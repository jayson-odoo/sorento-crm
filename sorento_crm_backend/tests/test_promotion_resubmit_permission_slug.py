"""The Promotions page gates its Resubmit bulk action on a permission slug.

The frontend hardcodes that string. If the registry ever stops issuing it - renamed,
split, or moved to a different generator - `useHasPermission` returns false for
everyone and the action silently vanishes from the toolbar, which reads as "the
feature was never built" rather than as a permissions problem. That already happened
once against the non-existent `marketing.promotions.update`.

Pinning it here makes the rename break a test instead of the UI.
"""
from app.rbac.permission_registry import PERMISSION_REGISTRY

# Must match `canResubmit` in
# sorento_crm_frontend/app/(protected)/marketing-management/promotions/components/PromotionsList.tsx
RESUBMIT_GATE_SLUG = "marketing.promotions.edit"


def test_the_resubmit_gate_slug_is_issued_by_the_registry():
    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert RESUBMIT_GATE_SLUG in slugs, (
        f"{RESUBMIT_GATE_SLUG} is gone from the registry; the Promotions Resubmit "
        "action will disappear for every user until the frontend slug is updated"
    )


def test_the_slug_the_frontend_originally_guessed_still_does_not_exist():
    """Guards the fix: if `.update` is ever introduced as an alias, the comment above
    stops being true and this test should be revisited deliberately."""
    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert "marketing.promotions.update" not in slugs
