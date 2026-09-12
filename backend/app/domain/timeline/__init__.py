"""The medical timeline — the problem statement's dated-history requirement.

Three modules, and the split is the safety property:

- `model.py` — the structures, including the status a report must always print.
- `fallback.py` — the timeline **pure code builds on its own**. This is what
  ships by default, with no provider configured and no model involved.
- `validate.py` — the gate a model's proposals pass through before they can
  reach a physician. Pure, exhaustively testable, and the only place the
  guarantees about model output live.

A provider can only ever narrow what `fallback.py` already found. So the worst
case for the whole feature is a physician seeing more history than they needed,
never one seeing something that did not happen.
"""
