#!/usr/bin/env bash
# Deploy both Cloud Run services from the one image, then point the Pub/Sub push
# subscription at the worker.
#
# Order matters and is not incidental: 35-migrate.sh has already moved the
# schema, so these revisions start against a database they understand. Running
# this without it deploys code that expects columns which do not exist yet.
#
# Two services, one image. They differ only in environment:
#
#   API     public, PUBSUB_PUSH_ENABLED unset, so the worker route does not
#           exist on it at all — an endpoint that is absent cannot be probed.
#   worker  --no-allow-unauthenticated, PUBSUB_PUSH_ENABLED=true, invoked only
#           by the push subscription's service account, and holding a shared
#           secret behind that as a second lock.

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

TAG="${TAG:-$(cat .last-image-tag 2>/dev/null || echo latest)}"
IMAGE="${IMAGE_BASE}:${TAG}"

common=(
  --image="${IMAGE}"
  --region="${REGION}"
  --platform=managed
  --network="${VPC_NETWORK}"
  --subnet="${VPC_SUBNET}"
  # Only private ranges go through the VPC. Vertex and the Google APIs keep
  # taking the default path, so a database on a private IP does not mean paying
  # for a NAT gateway to reach anything else.
  --vpc-egress=private-ranges-only
)

# One env string per service rather than a shared flag plus an override: gcloud
# takes the *last* --set-env-vars on the command line and discards the earlier
# one, so a `common` array holding one and the worker adding another would
# silently deploy the worker with nothing but PUBSUB_PUSH_ENABLED set.
#
# `^;^` picks semicolon as the separator, because some values contain commas
# and none contains a semicolon.
ENV_SHARED="ENVIRONMENT=${DEPLOY_ENVIRONMENT};CLINICAL_CONTENT_DIR=/app/clinical;LOG_JSON=true;STORAGE_BACKEND=gcs;GCS_BUCKET=${BUCKET};GCP_PROJECT=${PROJECT_ID};DOCUMENT_QUEUE=pubsub;PUBSUB_TOPIC=${TOPIC};VERTEX_PROJECT=${PROJECT_ID};VERTEX_REGION=${REGION};ALLOW_HEADER_AUTH=false"

# Which providers this revision runs. Both services get the same string: they
# run the same image, `/readyz` on either has to say what that service would
# actually do, and a worker that reports `ocr: mock` while reading documents
# with a model is worse than no report at all.
#
# `config.sh` has already refused the deploy if a cloud provider was selected
# without ZDR or without a model id, so by here these are either the mocks or a
# combination somebody decided on.
ENV_MODELS="OCR_PROVIDER=${OCR_PROVIDER};REPAIR_PROVIDER=${REPAIR_PROVIDER};VERTEX_ZDR_ENABLED=${VERTEX_ZDR_ENABLED}"
[[ -n "${OCR_MODEL_ID}" ]] && ENV_MODELS="${ENV_MODELS};OCR_MODEL_ID=${OCR_MODEL_ID}"
[[ -n "${REPAIR_MODEL_ID}" ]] && ENV_MODELS="${ENV_MODELS};REPAIR_MODEL_ID=${REPAIR_MODEL_ID}"
ENV_SHARED="${ENV_SHARED};${ENV_MODELS}"

# Repair runs on the API, during ingest, not on the worker — a payload that
# fails its contract has to be repaired before the response, and there is no
# document involved. So the API needs Vertex access too, which the provisioning
# script only grants the worker. Idempotent, and skipped entirely when repair is
# a mock, so a mock-only deployment does not quietly acquire the permission.
if [[ "${REPAIR_PROVIDER}" == "vertex" ]]; then
  say "Granting ${API_SERVICE} access to Vertex (REPAIR_PROVIDER=vertex)"
  gc projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${API_SA}" \
    --role=roles/aiplatform.user --condition=None >/dev/null
  echo "    ${API_SA%%@*} -> roles/aiplatform.user"
fi

# --- API --------------------------------------------------------------------
# min-instances 0: an OPD is not a 24-hour service and a cold start between
# patients costs nobody anything.
say "Deploying ${API_SERVICE}"
gc run deploy "${API_SERVICE}" "${common[@]}" \
  --service-account="${API_SA}" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=80 \
  --cpu=1 --memory=1Gi \
  --timeout=120s \
  --set-env-vars="^;^${ENV_SHARED}" \
  --set-secrets="DATABASE_URL=${SECRET_DATABASE_URL}:latest,KIOSK_TOKENS=${SECRET_KIOSK_TOKENS}:latest,PATIENT_REF_PEPPER=${SECRET_PATIENT_PEPPER}:latest"

API_URL="$(gc run services describe "${API_SERVICE}" --region="${REGION}" --format='value(status.url)')"

# --- worker -----------------------------------------------------------------
# Separate because OCR is bursty and the API is not: the worker scales to zero
# between patients, and the API never has to hold a request open while a model
# reads a photograph. More memory and a longer timeout for the same reason.
# The worker's ceiling is 10, not 20: with direct VPC egress attached, Cloud Run
# requires `maxScale` to be within the project's VPC-connected instance quota,
# which is 10 on a new project — and it rejects the deploy rather than clamping.
# OCR is queue-driven and Pub/Sub redelivers, so a lower ceiling costs latency
# under a burst, not work.
#
# Auth is the subscription's OIDC token (see the push-subscription block below)
# checked by Cloud Run against this service's `--no-allow-unauthenticated` and
# the `run.invoker` grant to the push SA — one control, and the real one. The
# worker also has an optional static-token check (`worker.py`), but that reads
# the same `Authorization` header the OIDC JWT now occupies, so binding
# `PUBSUB_PUSH_TOKEN` here made every push a 403. It is deliberately not set.
say "Deploying ${WORKER_SERVICE}"
gc run deploy "${WORKER_SERVICE}" "${common[@]}" \
  --service-account="${WORKER_SA}" \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=4 \
  --cpu=2 --memory=2Gi \
  --timeout=540s \
  --set-env-vars="^;^${ENV_SHARED};PUBSUB_PUSH_ENABLED=true" \
  --set-secrets="DATABASE_URL=${SECRET_DATABASE_URL}:latest"

WORKER_URL="$(gc run services describe "${WORKER_SERVICE}" --region="${REGION}" --format='value(status.url)')"

# --- push subscription ------------------------------------------------------
say "Pub/Sub push subscription"

# The push identity may invoke the worker and nothing else.
gc run services add-iam-policy-binding "${WORKER_SERVICE}" \
  --region="${REGION}" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role=roles/run.invoker >/dev/null

# Pub/Sub's own agent needs to be able to mint tokens as that identity.
PROJECT_NUMBER="$(gc projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
gc iam service-accounts add-iam-policy-binding "${PUBSUB_SA}" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role=roles/iam.serviceAccountTokenCreator >/dev/null

PUSH_ENDPOINT="${WORKER_URL}/api/v1/worker/documents"

sub_args=(
  --push-endpoint="${PUSH_ENDPOINT}"
  --push-auth-service-account="${PUBSUB_SA}"
  # The worker answers 204 for done-or-undoable and 5xx for try-again, so this
  # backoff is the retry policy for genuinely transient failures only.
  --ack-deadline=300
  --min-retry-delay=10s
  --max-retry-delay=600s
  --dead-letter-topic="${DEAD_LETTER_TOPIC}"
  # Five attempts, then the message goes to the dead-letter topic where a person
  # can look at it. A document that cannot be read is a document somebody has to
  # be told about, not one that retries silently for seven days.
  --max-delivery-attempts=5
)

if exists gc pubsub subscriptions describe "${SUBSCRIPTION}"; then
  gc pubsub subscriptions update "${SUBSCRIPTION}" "${sub_args[@]}"
  skip "${SUBSCRIPTION} (updated)"
else
  gc pubsub subscriptions create "${SUBSCRIPTION}" --topic="${TOPIC}" "${sub_args[@]}"
  made "${SUBSCRIPTION}"
fi

# Dead-lettering needs the Pub/Sub agent to be able to publish to the dead
# topic and to ack on the subscription; without both, delivery attempts are
# counted and then nothing happens.
gc pubsub topics add-iam-policy-binding "${DEAD_LETTER_TOPIC}" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role=roles/pubsub.publisher >/dev/null
gc pubsub subscriptions add-iam-policy-binding "${SUBSCRIPTION}" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role=roles/pubsub.subscriber >/dev/null

# --- smoke ------------------------------------------------------------------
say "Checking the deployment"
if curl -fsS "${API_URL}/readyz" >/dev/null; then
  echo "    /readyz ok"
else
  echo "    /readyz FAILED — the revision is live but not ready." >&2
  echo "    curl ${API_URL}/readyz to see which check failed." >&2
  exit 1
fi

# The worker route must not exist on the public service. This is the assertion
# that the two-service split is actually doing what it is for, and it is cheap
# enough to make on every deploy.
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${API_URL}/api/v1/worker/documents" -d '{}' -H 'content-type: application/json')"
if [[ "${code}" != "404" ]]; then
  echo "    SECURITY: the worker route answered ${code} on the public API." >&2
  echo "    It must be 404 there. Check PUBSUB_PUSH_ENABLED on ${API_SERVICE}." >&2
  exit 1
fi
echo "    worker route absent from the public API (404) — as intended"

say "Deployed ${TAG}"
echo "  env    ${DEPLOY_ENVIRONMENT}"
echo "  ocr    ${OCR_PROVIDER}"
echo "  repair ${REPAIR_PROVIDER}"
if [[ "${uses_cloud_models}" == "true" ]]; then
  echo "  NOTE: this revision sends patient documents and patient answers to"
  echo "        Vertex in ${REGION}. VERTEX_ZDR_ENABLED=true is your assertion."
fi
if [[ "${DEPLOY_ENVIRONMENT}" != "production" ]]; then
  echo "  WARNING: ENVIRONMENT=${DEPLOY_ENVIRONMENT} with the mock OTP sender."
  echo "           The sign-in response carries the six-digit code, so anyone"
  echo "           who knows a phone number can sign in as that patient. This is"
  echo "           for testing the app against a deployment holding no real"
  echo "           records. Redeploy without DEPLOY_ENVIRONMENT before it does."
fi
echo "  API    ${API_URL}"
echo "  worker ${WORKER_URL} (not publicly invocable)"
