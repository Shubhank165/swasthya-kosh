#!/usr/bin/env bash
# Build and push the image. One image serves the API, the worker and the
# migration job, so this runs once per release and the tag it prints is the
# thing every later step deploys.
#
# The tag is the git commit, not `latest`. A Cloud Run revision that says
# `:latest` cannot be traced back to a diff, and "which build is in production"
# is the first question asked when something goes wrong.

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)}"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  # Not fatal â€” the demo path builds from a dirty tree constantly â€” but the
  # tag then names a commit whose content is not what was built, and that is
  # worth one line of noise.
  echo "WARNING: working tree is dirty; ${TAG} does not describe what is in this image" >&2
  TAG="${TAG}-dirty"
fi

say "Building ${IMAGE_BASE}:${TAG}"

# Pre-pull the cache tag if it exists, so the --cache-from above has something.
gc artifacts docker images describe "${IMAGE_BASE}:latest" >/dev/null 2>&1 || true

gc builds submit \
  --region="${REGION}" \
  --config=infra/gcp/cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE_BASE},_TAG=${TAG}" \
  .

say "Built ${IMAGE_BASE}:${TAG}"
echo "${TAG}" > .last-image-tag
echo "Tag written to .last-image-tag; the migrate and deploy steps read it."
