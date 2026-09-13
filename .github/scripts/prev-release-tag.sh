#!/usr/bin/env bash
set -euo pipefail

# Resolves the previous release tag for the plugin whose *next* tag is given
# as $1, reading the full tag list on stdin (one tag per line, any order).
# Prints the single highest-semver-precedence candidate, or nothing (exit 0)
# when the candidate set is empty (first release). See
# .adev/21-1/plan.md Approach step 2 / #19 Amendment §2-3.
#
# Usage: git tag --list "${PLUGIN}--v*" | prev-release-tag.sh "$TAG"
#
# A candidate is a stdin line matching exactly "${PLUGIN}--v<strict-semver>",
# where PLUGIN is derived from the "--v"-prefixed tag being created ($1).
# That prefix match alone excludes src/* markers (different prefix entirely)
# and foreign-plugin tags (different plugin name); the tag being created
# itself and malformed/leading-zero versions are excluded explicitly below.
#
# SEMVER_RE is the strict semver grammar -- no leading zeros, no build
# metadata, numeric pre-release identifiers compared numerically. It is
# duplicated verbatim in release.yml's "Validate version is semver" step;
# Requirement 4 (tests/test_release_scripts.py::test_regex_parity) asserts
# the two stay byte-identical, so if you touch this string, touch that one
# too, in the same commit.
SEMVER_RE='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?$'

CREATING_TAG="${1:?usage: prev-release-tag.sh <tag-being-created> < tag-list}"
PLUGIN="${CREATING_TAG%--v*}"
PREFIX="${PLUGIN}--v"

# Width used to zero-pad every numeric field (major/minor/patch and numeric
# pre-release identifiers) so plain byte-wise sort compares them numerically
# instead of lexically (rc.10 must outrank rc.2; 0.10.0 must outrank 0.9.0).
# SEMVER_RE places no upper bound on how many digits a numeric field may
# have, so a fixed width could be overflowed by a pathological-but-valid tag
# and silently mis-sort it against normal-width versions. PAD therefore
# starts at a generous default and is grown below (before any sort key is
# computed) to the widest numeric field actually present across the
# creating tag and the whole candidate set, so it is always wide enough for
# this invocation.
PAD=20

# Force byte-wise (not locale-dependent) ordering for both the `sort` below
# and every `[[ ... > ... ]]` string comparison in this script -- the same
# guarantee the original code only applied to the final `sort` call.
export LC_ALL=C

# Terminator appended after every prerelease identifier's own encoded
# content (both the numeric and the alphanumeric branch in version_key()
# below), chosen as a byte strictly lower than any byte an identifier's
# content can legally contain. SEMVER_RE restricts prerelease identifier
# content to [0-9A-Za-z-], whose lowest byte is '-' (0x2D); '#' is 0x23, so
# it sorts below every legal content byte.
#
# Without this terminator, an identifier's own content butted directly
# against whatever came next (either the next identifier's leading '.'
# field-separator, or plain end-of-string), so a byte-wise sort key was not
# self-delimiting: an identifier ending in a byte lower than '.' (0x2E) --
# e.g. a trailing '-' -- could be compared against a *sibling* key's
# following '.' instead of against a real terminator, and '-' < '.' sorted
# it backwards. Concretely: "1.0.0-alpha-" (one identifier, "alpha-") must
# outrank "1.0.0-alpha.0" (two identifiers, "alpha" then "0") per SemVer
# 11.4.4 -- comparing first identifiers "alpha-" vs "alpha" alone settles
# it ("alpha" is a proper prefix of "alpha-", so "alpha-" is greater; the
# second identifier "0" is never even reached). The unterminated key
# instead compared "alpha-"'s own '-' against "alpha"'s follow-up '.'
# (leading the ".0<padded-0>" second identifier) and got '-' < '.', hence
# the wrong verdict. Terminating every identifier with a byte lower than
# any content byte makes "ends here" always sort below "keeps going",
# exactly matching SemVer's real prefix rule, regardless of what either
# side's next identifier (if any) happens to be.
ID_TERM='#'

# Prints the digit-width of the widest numeric field (major, minor, patch,
# or a numeric pre-release identifier) within $1, a version string already
# verified to match SEMVER_RE. Used only to size PAD -- never to build a
# sort key itself.
max_numeric_width() {
  local version="$1" core prerelease major rest minor patch max=0 len part id ids
  core="${version%%-*}"
  if [ "$core" = "$version" ]; then
    prerelease=""
  else
    prerelease="${version#*-}"
  fi
  major="${core%%.*}"
  rest="${core#*.}"
  minor="${rest%%.*}"
  patch="${rest#*.}"

  for part in "$major" "$minor" "$patch"; do
    len=${#part}
    [ "$len" -gt "$max" ] && max=$len
  done

  if [ -n "$prerelease" ]; then
    IFS='.' read -r -a ids <<<"$prerelease"
    for id in "${ids[@]}"; do
      if [[ "$id" =~ ^[0-9]+$ ]]; then
        len=${#id}
        [ "$len" -gt "$max" ] && max=$len
      fi
    done
  fi

  printf '%d' "$max"
}

# Left-pads $2 (a decimal digit string already verified by SEMVER_RE -- no
# sign, no leading-zero ambiguity to worry about) with zeros to width $1,
# using pure string manipulation rather than `printf '%0*d' width value`.
# That matters once PAD has grown to accommodate a pathologically wide
# numeral: `printf %d` converts its argument through a fixed-width integer
# type (intmax_t) first, which silently overflows/misconverts a value with
# more digits than that type can hold, corrupting the padded key regardless
# of how wide PAD is. Padding the digit string directly sidesteps that
# conversion entirely. If $2 is already at or beyond width $1, it is
# printed as-is (never truncated) -- PAD is always sized beforehand to be
# at least this wide, so this branch is defensive only.
zero_pad() {
  local width="$1" value="$2" pad_len
  pad_len=$((width - ${#value}))
  if [ "$pad_len" -le 0 ]; then
    printf '%s' "$value"
  else
    # The value being padded here is always the literal 0, whose width-N
    # zero-padded form is just N zero characters -- printf %d never risks
    # overflow here no matter how large pad_len is.
    printf '%0*d%s' "$pad_len" 0 "$value"
  fi
}

# Computes the sortable precedence key for $1, a version string already
# verified to match SEMVER_RE, and prints it. Factored out so the creating
# tag's own precedence (below) and each candidate's precedence (in the loop)
# are computed by the exact same logic -- two independently-written copies
# would risk silently drifting apart.
version_key() {
  local version="$1" core prerelease major rest minor patch key ids id
  core="${version%%-*}"
  if [ "$core" = "$version" ]; then
    prerelease=""
  else
    prerelease="${version#*-}"
  fi
  major="${core%%.*}"
  rest="${core#*.}"
  minor="${rest%%.*}"
  patch="${rest#*.}"

  key="$(zero_pad "$PAD" "$major").$(zero_pad "$PAD" "$minor").$(zero_pad "$PAD" "$patch")"

  if [ -z "$prerelease" ]; then
    # A release always outranks any prerelease sharing the same core
    # version: "1" here compares greater than the "0" the prerelease branch
    # starts with below, regardless of what (if anything) follows.
    key="${key}.1"
  else
    key="${key}.0"
    IFS='.' read -r -a ids <<<"$prerelease"
    for id in "${ids[@]}"; do
      if [[ "$id" =~ ^[0-9]+$ ]]; then
        # Numeric identifiers compare numerically and always have lower
        # precedence than alphanumeric ones -- "0" prefix sorts below "1".
        # ID_TERM after the zero-padded content is technically redundant
        # here (all numeric identifiers in one invocation share PAD's
        # fixed width, so numeric content alone is already unambiguous),
        # but it is appended anyway for uniformity with the alphanumeric
        # branch and so nothing relies on that fixed-width invariant only
        # holding for the numeric case.
        key="${key}.0$(zero_pad "$PAD" "$id")${ID_TERM}"
      else
        # ID_TERM after the raw content is what makes this branch safe --
        # see ID_TERM's own comment above for why an unterminated
        # variable-length identifier can sort incorrectly against a
        # sibling key's next dotted identifier.
        key="${key}.1${id}${ID_TERM}"
      fi
    done
  fi
  # A shorter identifier list is a plain string prefix of a longer one that
  # shares the same leading fields, and a prefix always sorts below its own
  # non-empty extension -- exactly semver's "more fields wins" rule, so no
  # explicit field-count padding is needed here. This only holds because
  # every identifier is self-terminated by ID_TERM: without it, "prefix" was
  # only true when the *literal characters* lined up, which broke down
  # exactly when one side's identifier list ended inside what looked like a
  # continuation of the other side's identifier content (see ID_TERM above).
  printf '%s' "$key"
}

# The creating tag's own precedence key. A candidate must be a genuine
# *predecessor* by semver precedence, never merely "not textually equal to
# the tag being created" -- e.g. if `agent-web-tester--v1.0.0` already
# exists and this invocation is creating a backport release
# `agent-web-tester--v0.9.1`, `1.0.0` postdates `0.9.1` and must never be
# selected as PREV_TAG even though it is the highest-precedence tag in the
# whole candidate set. Left empty (skipping precedence filtering, falling
# back to the exact-string self-exclusion below only) when the creating
# tag's own version half is not valid strict semver -- defensive only,
# since release.yml validates this before ever invoking this script.
creating_version="${CREATING_TAG#"$PREFIX"}"
creating_valid=0
if [[ "$creating_version" =~ $SEMVER_RE ]]; then
  creating_valid=1
fi

# Read all of stdin up front (it's a pipe -- consumable only once) and, in
# the same pass, apply every filter that does not depend on precedence
# (self-exclusion, prefix match, SEMVER_RE) so the two passes below --
# sizing PAD, then building sort keys -- both work from the same clean
# list instead of duplicating the filtering logic.
valid_versions=()
valid_lines=()
while IFS= read -r line || [ -n "$line" ]; do
  # Strip every CR (CRLF-terminated input, e.g. a Windows-authored tag list
  # -- or a test harness that double-translates an already-CRLF string on
  # write, which is what a naive single trailing-CR strip would miss). A
  # tag name never legitimately contains '\r', so removing all of them is
  # safe.
  line="${line//$'\r'/}"

  [ -z "$line" ] && continue
  [ "$line" = "$CREATING_TAG" ] && continue

  # Quoted prefix-stripping (never a glob) so a plugin name containing a
  # shell-glob-special character can't misbehave.
  stripped="${line#"$PREFIX"}"
  [ "$stripped" = "$line" ] && continue   # line didn't start with PREFIX

  [[ "$stripped" =~ $SEMVER_RE ]] || continue

  valid_versions+=("$stripped")
  valid_lines+=("$line")
done

# Size PAD to the widest numeric field seen anywhere in this invocation --
# the creating tag's own version plus every surviving candidate -- before
# computing a single sort key, so the fixed default only ever grows, never
# gets overflowed by a pathologically wide-but-valid numeric component.
if [ "$creating_valid" -eq 1 ]; then
  w=$(max_numeric_width "$creating_version")
  [ "$w" -gt "$PAD" ] && PAD=$w
fi
if [ "${#valid_versions[@]}" -gt 0 ]; then
  for version in "${valid_versions[@]}"; do
    w=$(max_numeric_width "$version")
    [ "$w" -gt "$PAD" ] && PAD=$w
  done
fi

creating_key=""
if [ "$creating_valid" -eq 1 ]; then
  creating_key=$(version_key "$creating_version")
fi

candidates=""

if [ "${#valid_versions[@]}" -gt 0 ]; then
  for i in "${!valid_versions[@]}"; do
    version="${valid_versions[$i]}"
    line="${valid_lines[$i]}"

    key=$(version_key "$version")

    # Only a candidate with strictly LOWER precedence than the tag being
    # created is eligible -- a same-or-higher-precedence tag is never a
    # "previous" release, however it happens to sort in tag-creation order.
    if [ -n "$creating_key" ] && [[ "$key" == "$creating_key" || "$key" > "$creating_key" ]]; then
      continue
    fi

    candidates="${candidates}${key}"$'\t'"${line}"$'\n'
  done
fi

[ -z "$candidates" ] && exit 0

printf '%s' "$candidates" | sort | tail -n1 | cut -f2-
