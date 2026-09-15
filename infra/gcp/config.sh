#!/usr/bin/env bash
# Shared settings and helpers for the deployment scripts. Sourced, not run.
#
# Everything is `asia-south1`. Not as a default â€” as a constraint. Patient data
# for an Indian hospital stays in India, which means the database, the bucket,
# the queue, both Cloud Run services and the model endpoint are all in region,
# and there is no variable here that lets one of them quietly not be.

set -euo pipefail

REGION="${REGION:-asia-south1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set and gcloud has no default project." >&2
  echo "  PROJECT_ID=my-project make provision" >&2
  exit 1
fi

case "${REGION}" in
  asia-south1|asia-south2) ;;
  *)
    echo "REGION is ${REGION}. This deployment is India-only by policy:" >&2
    echo "patient data and the models that read it stay in asia-south1 or" >&2
    echo "asia-south2. Changing that is a decision for the team, not a flag." >&2
    exit 1
    ;;
esac

# --- names ------------------------------------------------------------------
# Deterministic, so every script addresses the same resources and re-running any
# of them is a no-op rather than a second copy of something.
AR_REPO="${AR_REPO:-medikiosk}"
IMAGE_NAME="${IMAGE_NAME:-medikiosk}"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}"

SQL_INSTANCE="${SQL_INSTANCE:-medikiosk-pg}"
SQL_DATABASE="${SQL_DATABASE:-medikiosk}"
SQL_USER="${SQL_USER:-medikiosk}"
# The database is the one resource here that costs money whether or not anybody
# uses it: Cloud Run scales to zero, Cloud SQL does not.
#
# `db-g1-small` is a shared-core tier at roughly a third the price of the
# dedicated-core `db-custom-1-3840` this used to default to, and it is ample for
# an OPD's intake volume â€” the workload is a few hundred small writes a day, not
# a transaction system. Raise it for a real deployment; the knob is here so that
# is a decision somebody makes rather than a default nobody read.
SQL_TIER="${SQL_TIER:-db-g1-small}"

# Point-in-time recovery keeps write-ahead logs and bills for them, and it is
# not supported on every shared-core tier. On by default because losing a day of
# intakes is worse than the storage; off for a demo deployment on a budget.
SQL_PITR="${SQL_PITR:-true}"

BUCKET="${BUCKET:-${PROJECT_ID}-medikiosk-documents}"

TOPIC="${TOPIC:-medikiosk-documents}"
SUBSCRIPTION="${SUBSCRIPTION:-medikiosk-documents-push}"
DEAD_LETTER_TOPIC="${DEAD_LETTER_TOPIC:-medikiosk-documents-dead}"

API_SERVICE="${API_SERVICE:-medikiosk-api}"
WORKER_SERVICE="${WORKER_SERVICE:-medikiosk-worker}"
MIGRATE_JOB="${MIGRATE_JOB:-medikiosk-migrate}"

API_SA="medikiosk-api@${PROJECT_ID}.iam.gserviceaccount.com"
WORKER_SA="medikiosk-worker@${PROJECT_ID}.iam.gserviceaccount.com"
PUBSUB_SA="medikiosk-pubsub@${PROJECT_ID}.iam.gserviceaccount.com"

# Secret Manager. No value for any of these appears in this repository, in an
# image, in an environment variable set at build time, or in a log line.
SECRET_DATABASE_URL="${SECRET_DATABASE_URL:-medikiosk-database-url}"
SECRET_KIOSK_TOKENS="${SECRET_KIOSK_TOKENS:-medikiosk-kiosk-tokens}"
SECRET_PUSH_TOKEN="${SECRET_PUSH_TOKEN:-medikiosk-pubsub-push-token}"
# The pepper for patient phone references (2/3 Â§7.1). Without it the backend
# refuses to issue a patient session at all â€” a stored HMAC with no pepper is a
# plain digest of a ten-digit number, and a ten-digit space is a rainbow table.
# Generated at provision time and never printed, unlike the kiosk tokens, which
# have to be typed into devices.
SECRET_PATIENT_PEPPER="${SECRET_PATIENT_PEPPER:-medikiosk-patient-ref-pepper}"

# --- environment ------------------------------------------------------------
# `production` everywhere it matters, and the one thing in the backend that keys
# off it is the one that matters most: `PatientAuthService` returns the
# six-digit OTP in the sign-in response when the sender is the mock **and** the
# environment is not production. Outside production that is what lets a demo on
# a laptop with no signal complete a sign-in; inside it, it would hand anyone
# who knows a phone number a session as that patient.
#
# So it is a knob, because testing the app against a real deployment needs one,
# and it is a knob that says what it costs on every deploy that uses it.
DEPLOY_ENVIRONMENT="${DEPLOY_ENVIRONMENT:-production}"

# --- models -----------------------------------------------------------------
# Which providers this deployment runs, and the preconditions for the cloud
# ones. Defaults are the mocks, because a deployment that reaches a model by
# default is a deployment nobody decided to make.
#
# There is no model id here. `OCR_MODEL_ID` and `REPAIR_MODEL_ID` are supplied
# at deploy time and refused if missing â€” the same rule as everywhere else in
# this repository: a model is configuration, not a literal, so changing one is a
# deployment change with a name on it rather than a commit.
OCR_PROVIDER="${OCR_PROVIDER:-mock}"
REPAIR_PROVIDER="${REPAIR_PROVIDER:-mock}"
# Prefill's own default is `mock`, not `none` — with no provider every question
# is simply asked, which is what happened before the feature existed. It is
# named here anyway: it was omitted from the deploy string entirely, so every
# revision served `prefill: mock` no matter what the operator intended, and a
# setting that cannot be set is not a default, it is a bug.
PREFILL_PROVIDER="${PREFILL_PROVIDER:-mock}"
OCR_MODEL_ID="${OCR_MODEL_ID:-}"
REPAIR_MODEL_ID="${REPAIR_MODEL_ID:-}"
PREFILL_MODEL_ID="${PREFILL_MODEL_ID:-}"

# Zero Data Retention. This is an assertion the operator makes about the
# project; nothing here can verify it, and the adapters refuse to construct
# without it (see `app/adapters/ocr/gemini.py`). It is a separate flag from the
# provider precisely so that turning a model on is two decisions, not one.
VERTEX_ZDR_ENABLED="${VERTEX_ZDR_ENABLED:-false}"

uses_cloud_models=false
[[ "${OCR_PROVIDER}" == "gemini" || "${REPAIR_PROVIDER}" == "vertex" \
  || "${PREFILL_PROVIDER}" == "vertex" ]] && uses_cloud_models=true

if [[ "${uses_cloud_models}" == "true" ]]; then
  if [[ "${VERTEX_ZDR_ENABLED}" != "true" ]]; then
    echo "OCR_PROVIDER=${OCR_PROVIDER} REPAIR_PROVIDER=${REPAIR_PROVIDER}" >&2
    echo "PREFILL_PROVIDER=${PREFILL_PROVIDER} sends" >&2
    echo "patient documents and patient answers to a model, and" >&2
    echo "VERTEX_ZDR_ENABLED is not true. Confirm Zero Data Retention for" >&2
    echo "${PROJECT_ID} in ${REGION} first, then set it explicitly." >&2
    exit 1
  fi
  if [[ "${OCR_PROVIDER}" == "gemini" && -z "${OCR_MODEL_ID}" ]]; then
    echo "OCR_PROVIDER=gemini needs OCR_MODEL_ID. The model id is not in this" >&2
    echo "repository by design; pass it on the deploy command." >&2
    exit 1
  fi
  if [[ "${REPAIR_PROVIDER}" == "vertex" && -z "${REPAIR_MODEL_ID}" ]]; then
    echo "REPAIR_PROVIDER=vertex needs REPAIR_MODEL_ID." >&2
    exit 1
  fi
  if [[ "${PREFILL_PROVIDER}" == "vertex" && -z "${PREFILL_MODEL_ID}" ]]; then
    echo "PREFILL_PROVIDER=vertex needs PREFILL_MODEL_ID." >&2
    exit 1
  fi
fi

VPC_NETWORK="${VPC_NETWORK:-default}"
VPC_SUBNET="${VPC_SUBNET:-default}"
PRIVATE_RANGE_NAME="${PRIVATE_RANGE_NAME:-medikiosk-sql-range}"

# --- helpers ----------------------------------------------------------------

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
skip() { printf '    (exists) %s\n' "$*"; }
made() { printf '    created  %s\n' "$*"; }

# `exists <describe command...>` â€” true when the resource is already there.
# Every create in these scripts is wrapped in one, which is what makes running
# any script twice safe. A half-finished provision is the normal case, not the
# exceptional one: quotas, org policies and permissions all fail partway.
exists() { "$@" >/dev/null 2>&1; }

gc() { gcloud --project="${PROJECT_ID}" "$@"; }
