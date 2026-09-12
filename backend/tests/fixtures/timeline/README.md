# Timeline fixtures

Drafts the mock provider returns, keyed by **scenario name** — the value of
`today["scenario"]` in the request.

Not keyed by a digest of the request. A digest-keyed fixture invalidates the
moment anything about serialisation changes — a field added, a key reordered —
and the failure reads as "the mock stopped working" rather than "the fixture is
stale", which is a morning lost. The OCR fixtures are digest-keyed and this is
the lesson from them.

With no fixture matching, `MockTimelineProvider` falls back to a rule a human can
read: candidates sharing a coded tag with today's complaint score 0.9, the rest
are omitted. That is enough to exercise the whole relevance path — including the
foot injury under a fever complaint — without a fixture per case.

A fixture is a `TimelineDraft`: `{"events": [...], "omitted_count": n}`. Every
event still passes `validate.py`, so a fixture cannot smuggle an unknown
`candidate_id` or a contradicted date onto a report any more than a model can.
