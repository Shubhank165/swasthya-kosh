"""Provider adapters.

`protocols.py` defines every seam a cloud provider will later plug into;
`mocks.py` holds the deterministic implementations this build runs on. They are
two flat modules rather than a package per provider: eight packages holding one
class each would be filing, not structure, and the protocols are more legible
read together than scattered.

`fhir/` is a package because its mapper is a real implementation with enough
substance to warrant its own module.
"""
