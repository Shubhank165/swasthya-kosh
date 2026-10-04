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

# **No `--args` here.** It is passed per invocation by `run_job` below, because
# `--args` accumulates rather than replaces: a second `--args=seed` after an
# `--args=migrate` in this array produced the entrypoint command
# `migrate seed`, which runs the migrations and silently ignores the rest. The
# `SEED=true` path therefore ran alembic three times and never seeded, and said
# "Seeding" while doing it — the schema moved, the demo facility never
# appeared, and nothing failed.
job_args=(
  --image="${IMAGE}"
  --region="${REGION}"
  --service-account="${API_SA}"
  --max-retries=0
  --task-timeout=600s
  --set-secrets="DATABASE_URL=${SECRET_DATABASE_URL}:latest"
  --set-env-vars="ENVIRONMENT=production,CLINICAL_CONTENT_DIR=/app/clinical"
  --network="${VPC_NETWORK}"
  --subnet="${VPC_SUBNET}"
  --vpc-egress=private-ranges-only
)

#: Point the job at one entrypoint command and run it to completion.
#:
#: `--wait`, so a failure fails this script and the deploy that depends on it
#: never runs.
run_job() {
  local command="$1"
  if exists gc run jobs describe "${MIGRATE_JOB}" --region="${REGION}"; then
    gc run jobs update "${MIGRATE_JOB}" "${job_args[@]}" --args="${command}"
  else
    gc run jobs create "${MIGRATE_JOB}" "${job_args[@]}" --args="${command}"
  fi
  gc run jobs execute "${MIGRATE_JOB}" --region="${REGION}" --wait
}

run_job migrate

say "Schema is at head"

# The seeder is separate and optional: it writes the demo facility, the
# department list and the terminology tables. Idempotent, so re-running it
# against a live database is safe, but it is not part of a deploy.
if [[ "${SEED:-false}" == "true" ]]; then
  say "Seeding"
  run_job seed
  # Leave the job pointing at `migrate`, so that anyone who executes it from the
  # console gets the step this job is named for rather than the last one it
  # happened to run.
  gc run jobs update "${MIGRATE_JOB}" "${job_args[@]}" --args=migrate >/dev/null
  say "Seeded"
fi
