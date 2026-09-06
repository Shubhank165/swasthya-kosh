#!/usr/bin/env bash
# Create everything the deployment needs. Idempotent: run it as many times as
# you like, including after it fails halfway, which it will the first time
# because some API was not enabled yet.
#
# It deliberately does NOT create the Pub/Sub push subscription. A push
# subscription needs the worker's URL, and the worker does not exist until
# 40-deploy.sh has run — so that script owns the subscription. Creating it here
# with a guessed URL would produce a subscription that pushes into nothing and
# retries for seven days.
#
#   PROJECT_ID=my-project infra/gcp/00-provision.sh

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

say "Project ${PROJECT_ID}, region ${REGION}"

if [[ "${SQL_PITR}" == "true" ]]; then
  SQL_PITR_FLAG="--enable-point-in-time-recovery"
else
  SQL_PITR_FLAG="--no-enable-point-in-time-recovery"
  say "Point-in-time recovery is OFF (SQL_PITR=false)"
fi

# --- APIs -------------------------------------------------------------------
say "Enabling APIs"
gc services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  pubsub.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com

# --- service accounts -------------------------------------------------------
# Three, not one. The API can read documents and publish jobs; the worker can
# read and write them and reach Vertex; the push identity can do nothing except
# invoke the worker. A single shared account would make the blast radius of a
# leaked worker credential the whole system.
say "Service accounts"
for pair in "medikiosk-api:MediKiosk API" \
            "medikiosk-worker:MediKiosk OCR worker" \
            "medikiosk-pubsub:MediKiosk Pub/Sub push identity"; do
  name="${pair%%:*}"; desc="${pair#*:}"
  if exists gc iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com"; then
    skip "${name}"
  else
    gc iam service-accounts create "${name}" --display-name="${desc}"
    made "${name}"
  fi
done

# --- Artifact Registry ------------------------------------------------------
say "Artifact Registry"
if exists gc artifacts repositories describe "${AR_REPO}" --location="${REGION}"; then
  skip "${AR_REPO}"
else
  gc artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="MediKiosk container images"
  made "${AR_REPO}"
fi

# --- private services access ------------------------------------------------
# Cloud SQL gets a private IP and no public one, so the database is not on the
# internet at all. That needs a reserved range peered to the VPC; both steps are
# one-time and both are safe to repeat.
say "Private services access for Cloud SQL"
if exists gc compute addresses describe "${PRIVATE_RANGE_NAME}" --global; then
  skip "${PRIVATE_RANGE_NAME}"
else
  gc compute addresses create "${PRIVATE_RANGE_NAME}" \
    --global \
    --purpose=VPC_PEERING \
    --prefix-length=16 \
    --network="${VPC_NETWORK}"
  made "${PRIVATE_RANGE_NAME}"
fi

if gc services vpc-peerings list --network="${VPC_NETWORK}" \
     --format='value(reservedPeeringRanges)' 2>/dev/null \
   | grep -q "${PRIVATE_RANGE_NAME}"; then
  skip "vpc peering"
else
  gc services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges="${PRIVATE_RANGE_NAME}" \
    --network="${VPC_NETWORK}"
  made "vpc peering"
fi

# --- Cloud SQL --------------------------------------------------------------
say "Cloud SQL"
if exists gc sql instances describe "${SQL_INSTANCE}"; then
  skip "${SQL_INSTANCE}"
else
  # No public IP. Deletion protection on: this holds patient records, and the
  # cost of an accidental `gcloud sql instances delete` is not recoverable from
  # a backup that was taken after the delete.
  # `--edition=ENTERPRISE` explicitly: gcloud now defaults Postgres 16 to
  # ENTERPRISE_PLUS, which accepts only `db-perf-optimized-*` machine types and
  # rejects every shared-core tier. The default silently triples the bill of the
  # one resource here that runs whether or not anybody uses it.
  gc sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_16 \
    --edition=ENTERPRISE \
    --region="${REGION}" \
    --tier="${SQL_TIER}" \
    --storage-auto-increase \
    --network="projects/${PROJECT_ID}/global/networks/${VPC_NETWORK}" \
    --no-assign-ip \
    --backup-start-time=19:30 \
    ${SQL_PITR_FLAG} \
    --deletion-protection
  made "${SQL_INSTANCE}"
fi

if exists gc sql databases describe "${SQL_DATABASE}" --instance="${SQL_INSTANCE}"; then
  skip "database ${SQL_DATABASE}"
else
  gc sql databases create "${SQL_DATABASE}" --instance="${SQL_INSTANCE}"
  made "database ${SQL_DATABASE}"
fi

# The password is generated here, written straight into Secret Manager, and
# never printed, never passed on a command line that shows up in `ps`, and never
# held in a shell variable that outlives this block.
if exists gc sql users describe "${SQL_USER}" --instance="${SQL_INSTANCE}"; then
  skip "user ${SQL_USER}"
else
  sql_password="$(openssl rand -base64 32 | tr -d '\n=' )"
  gc sql users create "${SQL_USER}" \
    --instance="${SQL_INSTANCE}" \
    --password="${sql_password}"
  private_ip="$(gc sql instances describe "${SQL_INSTANCE}" \
    --format='value(ipAddresses.filter("type:PRIVATE").extract("ipAddress").flatten())')"
  printf 'postgresql+asyncpg://%s:%s@%s:5432/%s' \
    "${SQL_USER}" "${sql_password}" "${private_ip}" "${SQL_DATABASE}" \
    | gc secrets create "${SECRET_DATABASE_URL}" \
        --replication-policy=user-managed --locations="${REGION}" --data-file=- \
    || printf 'postgresql+asyncpg://%s:%s@%s:5432/%s' \
         "${SQL_USER}" "${sql_password}" "${private_ip}" "${SQL_DATABASE}" \
       | gc secrets versions add "${SECRET_DATABASE_URL}" --data-file=-
  unset sql_password
  made "user ${SQL_USER} and secret ${SECRET_DATABASE_URL}"
fi

# --- Cloud Storage ----------------------------------------------------------
say "Document bucket"
if exists gc storage buckets describe "gs://${BUCKET}"; then
  skip "gs://${BUCKET}"
else
  # Uniform access, public access prevention enforced, and versioning on. These
  # are photographs of prescriptions: there is no configuration in which one of
  # them should be readable by an unauthenticated URL, so the bucket is not
  # capable of it rather than merely not configured for it.
  gc storage buckets create "gs://${BUCKET}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --default-storage-class=STANDARD
  gc storage buckets update "gs://${BUCKET}" --versioning
  made "gs://${BUCKET}"
fi

# --- Pub/Sub ----------------------------------------------------------------
say "Pub/Sub topics"
for t in "${TOPIC}" "${DEAD_LETTER_TOPIC}"; do
  if exists gc pubsub topics describe "${t}"; then
    skip "${t}"
  else
    gc pubsub topics create "${t}" --message-storage-policy-allowed-regions="${REGION}"
    made "${t}"
  fi
done

# --- Secret Manager ---------------------------------------------------------
# The kiosk tokens and the push token. The push token is generated here; the
# kiosk tokens are not, because they have to match what is flashed onto the
# devices and that is a human step.
say "Secrets"
if exists gc secrets describe "${SECRET_PUSH_TOKEN}"; then
  skip "${SECRET_PUSH_TOKEN}"
else
  openssl rand -hex 32 | tr -d '\n' \
    | gc secrets create "${SECRET_PUSH_TOKEN}" \
        --replication-policy=user-managed --locations="${REGION}" --data-file=-
  made "${SECRET_PUSH_TOKEN}"
fi

if exists gc secrets describe "${SECRET_KIOSK_TOKENS}"; then
  skip "${SECRET_KIOSK_TOKENS}"
else
  gc secrets create "${SECRET_KIOSK_TOKENS}" \
    --replication-policy=user-managed --locations="${REGION}"
  made "${SECRET_KIOSK_TOKENS} (no version yet)"
fi

if ! exists gc secrets versions describe latest --secret="${SECRET_KIOSK_TOKENS}"; then
  cat >&2 <<'NOTE'

    ACTION REQUIRED — the kiosk tokens secret has no version.

    One entry per kiosk device, mapping its token to the hospital it belongs
    to. The token's hospital is authoritative: it overrides anything in a
    request body, which is what stops a misconfigured device writing into
    another hospital's records.

    Generate the tokens where the devices are provisioned, then:

      printf '{"<token>":"<hospital_id>"}' | \
        gcloud secrets versions add medikiosk-kiosk-tokens --data-file=-

    Do not put a value in a file, a shell history, a ticket, or this repo.

NOTE
fi

# --- IAM --------------------------------------------------------------------
say "IAM"
grant() {  # grant <member> <role> [resource-specific args...]
  gc projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:$1" --role="$2" --condition=None >/dev/null
  printf '    %s -> %s\n' "${1%%@*}" "$2"
}

# Both services talk to Cloud SQL and read their own secrets. Only the worker
# calls Vertex, and only the API publishes jobs.
for sa in "${API_SA}" "${WORKER_SA}"; do
  grant "${sa}" roles/cloudsql.client
done
grant "${API_SA}" roles/pubsub.publisher
grant "${WORKER_SA}" roles/aiplatform.user

# Secrets are granted one at a time rather than project-wide: a service that can
# read every secret in the project is a service that can read the next one
# somebody adds.
secret_access() {  # secret_access <secret> <member>
  gc secrets add-iam-policy-binding "$1" \
    --member="serviceAccount:$2" --role=roles/secretmanager.secretAccessor >/dev/null
  printf '    %s -> read %s\n' "${2%%@*}" "$1"
}
secret_access "${SECRET_DATABASE_URL}" "${API_SA}"
secret_access "${SECRET_DATABASE_URL}" "${WORKER_SA}"
secret_access "${SECRET_KIOSK_TOKENS}" "${API_SA}"
secret_access "${SECRET_PUSH_TOKEN}" "${WORKER_SA}"

# Object-level, on the one bucket. The API writes uploads and signs read URLs;
# the worker reads what it was asked to read.
gc storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${API_SA}" --role=roles/storage.objectAdmin >/dev/null
gc storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${WORKER_SA}" --role=roles/storage.objectUser >/dev/null
printf '    api, worker -> gs://%s\n' "${BUCKET}"

# Signing a URL without a private key file: the service account impersonates
# itself through the IAM API, so no key material exists to leak.
gc iam service-accounts add-iam-policy-binding "${API_SA}" \
  --member="serviceAccount:${API_SA}" \
  --role=roles/iam.serviceAccountTokenCreator >/dev/null
printf '    api -> can sign its own URLs (no key file)\n'

say "Provisioned. Next: make build-image && make migrate-cloud && make deploy"
