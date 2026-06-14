"""References resolve: `domain` is accepted as an alias for `domain_hint`."""
from app.api.v1.system.references import ResolveReferenceRequest


def test_domain_alias_populates_domain_hint():
    req = ResolveReferenceRequest(**{"query": "x", "domain": "catalogue"})
    assert req.domain_hint == "catalogue"


def test_domain_hint_canonical_name_still_works():
    req = ResolveReferenceRequest(**{"query": "x", "domain_hint": "catalogue"})
    assert req.domain_hint == "catalogue"
