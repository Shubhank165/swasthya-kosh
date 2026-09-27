# Evaluation

    make evaluate            # the metrics table
    python -m evaluation.run --json

Runs every scenario in `scenarios/` through the real normaliser and the real
report builder — no database, no providers, no network — and prints what held.
Exits non-zero on any failure, so `make check` fails the build on a regression.

## What a scenario is

A kiosk payload, exactly as a device would send it, plus what must still be true
afterwards:

```yaml
scenarios:
  - id: five_statuses_01
    description: >
      Why this patient is worth having in the set.
    language: en
    payload:
      status: complete
      fields:
        tobacco: {value: null, status: refused, source_turn: 9}
    expect_fields:
      tobacco: refused          # all five statuses are in play
    expect_red_flags: []        # exactly what the device raised, no more
    expect_verbatim: ["pain in both knees"]
    forbid_assertions: ["non-smoker", "denies tobacco"]
```

`expect_red_flags` is checked in both directions. A criterion in the record that
the scenario did not send fails the run: this backend evaluates no rules, and a
flag it produced on its own is the one thing it may not do.

## What this does not measure

Which question was asked, and when. That is the walker on the Jetson, and a
number about it has to be produced there. See decision 78.

## Adding one

Write it, run `make evaluate`, and then **break it on purpose once** — change an
expected status and check the run goes red. A scenario that has only ever been
seen to pass has not been shown to be checking anything.
