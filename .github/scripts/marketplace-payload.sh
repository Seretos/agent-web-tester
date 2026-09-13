#!/usr/bin/env bash
set -euo pipefail

# Builds the repository_dispatch payload for agent-marketplace with
# `jq -n`, so a changelog containing quotes, backticks, `$(...)` or embedded
# newlines is JSON-escaped correctly -- an unquoted bash heredoc broke the
# marketplace once on exactly this shape of input (agent-marketplace@89aa850).
# See .adev/21-1/plan.md Approach step 5 / #19 Amendment §5, #17.
#
# All inputs come from the environment, never argv: a multi-line hostile
# changelog must never pass through shell word-splitting or argv limits.
#
# Required:  NAME, DESCRIPTION, REPO, CATEGORY, VERSION, TAG
# Optional:  CHANGELOG -- omitted entirely from client_payload.changelog
#            (not null, not "") when empty. This script only checks
#            CHANGELOG for emptiness; stripping its one trailing newline is
#            the caller's job (release.yml's "Dispatch to agent-marketplace"
#            step), done once, before invoking this script.

: "${NAME:?NAME must be set}"
: "${DESCRIPTION:?DESCRIPTION must be set}"
: "${REPO:?REPO must be set}"
: "${CATEGORY:?CATEGORY must be set}"
: "${VERSION:?VERSION must be set}"
: "${TAG:?TAG must be set}"
CHANGELOG="${CHANGELOG:-}"

# Same URL shape release.yml has always sent (icon/description_url resolve
# against the tagged commit on the orphan release branch).
ICON="https://raw.githubusercontent.com/${REPO}/${TAG}/assets/icon.png"
DESCRIPTION_URL="https://raw.githubusercontent.com/${REPO}/${TAG}/description.md"

if [ -n "$CHANGELOG" ]; then
  jq -n \
    --arg name "$NAME" \
    --arg description "$DESCRIPTION" \
    --arg repo "$REPO" \
    --arg category "$CATEGORY" \
    --arg version "$VERSION" \
    --arg ref "$TAG" \
    --arg icon "$ICON" \
    --arg description_url "$DESCRIPTION_URL" \
    --arg changelog "$CHANGELOG" \
    '{
      event_type: "plugin-release",
      client_payload: {
        name: $name,
        description: $description,
        repo: $repo,
        category: $category,
        version: $version,
        ref: $ref,
        icon: $icon,
        description_url: $description_url,
        changelog: $changelog
      }
    }'
else
  jq -n \
    --arg name "$NAME" \
    --arg description "$DESCRIPTION" \
    --arg repo "$REPO" \
    --arg category "$CATEGORY" \
    --arg version "$VERSION" \
    --arg ref "$TAG" \
    --arg icon "$ICON" \
    --arg description_url "$DESCRIPTION_URL" \
    '{
      event_type: "plugin-release",
      client_payload: {
        name: $name,
        description: $description,
        repo: $repo,
        category: $category,
        version: $version,
        ref: $ref,
        icon: $icon,
        description_url: $description_url
      }
    }'
fi
