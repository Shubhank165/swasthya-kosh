#!/usr/bin/env bash
# Run the migrations. **Before** the deploy, as its own step, with exactly one
# runner.
#
# This is the whole reason `serve` no longer migrates. With min-instances 0, a
# morning's first patients cold-start several API containers at once; each would
# run `alembic upgrade head` against the same database, and a rollback of the
# application would not be a rollback because the schema had already moved.
#
# A Cloud Run job, not a container that exits: it gets the same VPC egress and
# the same secret bindings as the services, so "it worked in the job" means the
# services can reach the database too.

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

TAG="${TAG:-$(cat .last-image-tag 2>/dev/null || echo latest)}"
IMAGE="${IMAGE_BASE}:${TAG}"

say "Migrating with ${IMAGE}"

job_args=(
  --image="${IMAGE}"
  --region="${REGION}"
  --service-account="${API_SA}"
  --args=migrate
  --max-retries=0
  --task-timeout=600s
  --set-secrets="DATABASE_URL=${SECRET_DATABASE_URL}:latest"
  --set-env-vars="ENVIRONMENT=production,CLINICAL_CONTENT_DIR=/app/clinical"
  --network="${VPC_NETWORK}"
  --subnet="${VPC_SUBNET}"
  --vpc-egress=private-ranges-only
)

if exists gc run jobs describe "${MIGRATE_JOB}" --region="${REGION}"; then
  gc run jobs update "${MIGRATE_JOB}" "${job_args[@]}"
else
  gc run jobs create "${MIGRATE_JOB}" "${job_args[@]}"
fi

# --wait, so a failed migration fails this script and the deploy that depends on
# it never runs.
gc run jobs execute "${MIGRATE_JOB}" --region="${REGION}" --wait

say "Schema is at head"

# The seeder is separate and optional: it writes the demo facility, the
# department list and the terminology tables. Idempotent, so re-running it
# against a live database is safe, but it is not part of a deploy.
if [[ "${SEED:-false}" == "true" ]]; then
  say "Seeding"
  gc run jobs update "${MIGRATE_JOB}" "${job_args[@]}" --args=seed
  gc run jobs execute "${MIGRATE_JOB}" --region="${REGION}" --wait
  gc run jobs update "${MIGRATE_JOB}" "${job_args[@]}"
fi
