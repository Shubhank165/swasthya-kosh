# Deploying to GCP

Four scripts, in order. All of them are idempotent — run any one twice and the
second run changes nothing — because the first attempt fails partway on quotas,
org policies or an API that was not enabled yet, and re-running is the normal
recovery rather than an exceptional one.

```bash
export PROJECT_ID=your-project        # or set gcloud's default project
make provision                        # 00-provision.sh — one time
gcloud secrets versions add medikiosk-kiosk-tokens --data-file=-   # see below
make deploy                           # check, build, migrate, deploy
```

`make deploy` runs `make check` first — ruff, mypy and the offline test suite —
then `30-build.sh`, then `35-migrate.sh`, then `40-deploy.sh`. Migrations happen
before any traffic moves, never at container start; `backend/infra-entrypoint.sh`
says why.

## What gets created

| Script | Creates |
|---|---|
| `00-provision.sh` | APIs, three service accounts, Artifact Registry, the private-services peering, Cloud SQL (private IP, no public IP), the documents bucket, two Pub/Sub topics, the secrets, and every IAM binding |
| `30-build.sh` | One image, tagged with the git commit, in Artifact Registry |
| `35-migrate.sh` | A Cloud Run job that runs `alembic upgrade head` and waits |
| `40-deploy.sh` | The API and worker Cloud Run services, and the push subscription |

The Pub/Sub push subscription is created by `40-deploy.sh`, not by
`00-provision.sh`, because it needs the worker's URL and the worker does not
exist until then. Creating it earlier with a guessed URL produces a subscription
that pushes into nothing and retries for seven days.

## Region

`asia-south1`. `config.sh` refuses anything outside `asia-south1` /
`asia-south2` rather than defaulting to them: patient data for an Indian
hospital staying in India is not a preference that gets overridden during a demo
at 2am.

## Secrets

Three, all in Secret Manager, none with a value anywhere in this repository:

| Secret | Set by | Read by |
|---|---|---|
| `medikiosk-database-url` | `00-provision.sh`, generated and written straight in | API, worker, migrate job |
| `medikiosk-pubsub-push-token` | `00-provision.sh`, generated | worker |
| `medikiosk-kiosk-tokens` | **you** | API |

The kiosk tokens are the one manual step, because they have to match what is
flashed onto the devices:

```bash
printf '{"<token>":"<hospital_id>"}' | \
  gcloud secrets versions add medikiosk-kiosk-tokens --data-file=-
```

One entry per device. The token's hospital is authoritative — it overrides
anything in a request body — which is what stops a misconfigured kiosk writing
into another hospital's records.

**The hospital id must already exist in the database.** A token naming a
hospital that was never seeded makes every ingest fail; the API says so by name
(`configuration_error`) rather than returning a bare 500, but it still fails.
Run the seeder first: `SEED=true make migrate-cloud`.

## The two services

Both run the same image and differ only in environment.

| | API | Worker |
|---|---|---|
| Reachable | public | `--no-allow-unauthenticated` |
| `PUBSUB_PUSH_ENABLED` | unset | `true` |
| Concurrency | 80 | 4 |
| Timeout | 120s | 540s |
| Secrets | database URL, kiosk tokens | database URL, push token |

The worker route does not exist on the API — the router is registered only when
`PUBSUB_PUSH_ENABLED` is set, so an endpoint that processes documents for an
arbitrary hospital id is absent rather than present-and-guarded. `40-deploy.sh`
asserts this on every deploy: if the public API answers anything but 404 for
`POST /api/v1/worker/documents`, the deploy fails.

## Before turning on cloud models

`OCR_PROVIDER=gemini` and `REPAIR_PROVIDER=vertex` are **not** set by these
scripts, and the adapters refuse to construct without `VERTEX_ZDR_ENABLED` and
an Indian region. There is an open residency question behind those guards —
decision 31 in `docs/DECISIONS.md` — and it has to be answered in writing before
either provider is switched on in an environment holding real patient data.

## Tearing down

There is no teardown script, deliberately. Cloud SQL is created with
`--deletion-protection`, and a one-command destroy for a database holding
patient records is a footgun with no upside. Delete things by hand, in the order
you meant to.
