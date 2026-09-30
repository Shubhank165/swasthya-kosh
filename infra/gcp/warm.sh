#!/usr/bin/env bash
# Wake the API before a demo.
#
# `40-deploy.sh` sets `--min-instances=0` and argues that a cold start between
# patients costs nobody anything. That is true of every route but one.
#
# **Prefill is the exception.** `POST /intakes/{id}/prefill` suggests answers to
# upcoming questions from what the patient just said, and it is best-effort by
# design: `PrefillRepository.suggest` in the app catches every failure and
# returns no suggestions, so the interview never waits on it. Which means a
# prefill that times out is indistinguishable, on screen, from a prefill that
# simply had nothing to suggest. The feature does not break — it silently stops
# existing, with nothing in any log to say so.
#
# Measured against the deployed service:
#
#     cold   9.4 s
#     warm   0.2 s
#
# and the app's `connectTimeout` is 10 s (`app/lib/core/api.dart`). A cold start
# lands close enough to that ceiling that the first patient of a session may get
# no suggestions at all.
#
# So: run this before a demo. It is not a fix, it is a warm-up, and the fix if
# this ever matters in a real deployment is `--min-instances=1` and the monthly
# cost that comes with it.
#
#     make warm
#     API_URL=https://... infra/gcp/warm.sh

set -euo pipefail

if [[ -n "${API_URL:-}" ]]; then
  URL="${API_URL}"
else
  source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
  URL="$(gcloud run services describe "${API_SERVICE}" \
    --region="${REGION}" --format='value(status.url)' 2>/dev/null || true)"
fi

if [[ -z "${URL}" ]]; then
  echo "No API URL. Set API_URL, or deploy first so the service can be found." >&2
  exit 1
fi

#: Above this, treat the container as still starting. Warm is ~0.2s, so 2s is
#: far enough above the noise to be unambiguous and far enough below a cold
#: start to catch one.
THRESHOLD="${WARM_THRESHOLD_S:-2.0}"
ATTEMPTS="${WARM_ATTEMPTS:-6}"

printf 'Warming %s\n' "${URL}"

for attempt in $(seq 1 "${ATTEMPTS}"); do
  elapsed="$(curl -s -o /dev/null -w '%{time_total}' --max-time 60 "${URL}/readyz" || echo 999)"
  printf '  attempt %d: %ss\n' "${attempt}" "${elapsed}"

  if awk "BEGIN { exit !($elapsed < $THRESHOLD) }"; then
    printf '\nWarm. Prefill will answer inside the app timeout.\n'
    exit 0
  fi
done

printf '\nStill slow after %d attempts. The service may be failing to start —\n' "${ATTEMPTS}"
printf 'check `gcloud run services logs read %s` before demoing.\n' "${API_SERVICE:-the API}" >&2
exit 1
