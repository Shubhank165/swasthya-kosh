"""Timeline providers — the one place prior consultation content could egress.

`mock` is fixture-backed and runs everywhere. `vertex` is config-gated and
refuses to construct outside an Indian region or without ZDR asserted, and
refuses to *run* on prior-intake candidates unless
`TIMELINE_SHARE_PRIOR_RECORDS` says so. `none` — the default — means pure code
builds the timeline and no model sees anything.
"""
