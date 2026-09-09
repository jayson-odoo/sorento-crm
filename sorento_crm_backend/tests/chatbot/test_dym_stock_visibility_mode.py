"""RED-phase tests for issue #768: DYM annotator ignoring `stock_visibility.mode`.

`_annotate`'s `qty_gt_zero` predicate (`app/services/chatbot/lanes/business/miss_suggest.py`)
sums a probe row's "Quantity On Hand" field, a label that exists ONLY in the stock tool's
`detailed` visibility mode. The MCP presenter's `compact` and `availability` modes shape rows
differently (`sorento_crm_mcp/sorento_crm_mcp/presenters.py::_stock_compact` /
`_stock_availability`), so today every non-detailed probe sums to zero and every candidate is
wrongly rendered "no stock details" even when it has stock.

Contract under test (see issue #768 for the full spec):
  1. `detailed` (or no stock_visibility/result_type at all): unchanged baseline behaviour.
  2. `compact`: available iff the row's "Total" field parses > 0. Per-location fields ignored.
     Twin codes (same code, different company, no Company field to tell them apart)
     ACCUMULATE their totals rather than overwrite.
  3. `availability`: ALWAYS fails open (`ok: False`, `reason: "availability_unknown"`,
     `dym_available_codes == []`) regardless of the row's flags - the probe never sends
     `requested_qty`, so `needs_quantity` is always true today, and even when it isn't
     `available` is a quantity verdict, not "has stock details".
  4. Unknown mode string: `ok: False`, `reason: "unknown_stock_mode"`, `dym_available_codes == []`.
  5. `dym_probe_meta["mode"]` records which mode was used (or the raw unknown string).

These tests were written BEFORE the fix (Phase 2 test-first) and revised after review found
the compact arm could overwrite a stocked twin with a zero-stock one, and that the
availability arm's flag-driven design could never be reached honestly.
"""

from app.services.chatbot.lanes.business.miss_suggest import dym_annotate
from app.services.chatbot.lanes.business.sub_answer import dym_annotate_partial


def _base_item(**extra):
    item = {
        "probe_predicate": "qty_gt_zero",
        "probe_tool": "crm_inventory_stock_balance_list",
        "probe_noun": "stock details",
        "dym_candidate_codes": ["SRTWC282", "SRTWC286-SH-P"],
    }
    item.update(extra)
    return item


# --------------------------------------------------------------------------- #
# AC 1: detailed mode (or no mode block at all) is unchanged - today's behaviour,
# and it must PASS right now (this is the baseline the other modes regress against).
# --------------------------------------------------------------------------- #


class TestDetailedModeUnchangedBaseline:
    def test_detailed_mode_sums_quantity_on_hand_per_code(self) -> None:
        item = _base_item(
            answers=[
                {
                    "title": "SRTWC282",
                    "fields": [
                        {"label": "Product Code", "value": "SRTWC282"},
                        {"label": "Quantity On Hand", "value": 6},
                    ],
                },
                {
                    "title": "SRTWC286-SH-P",
                    "fields": [
                        {"label": "Product Code", "value": "SRTWC286-SH-P"},
                        {"label": "Quantity On Hand", "value": 0},
                    ],
                },
            ],
        )
        out = dym_annotate(item)
        assert out["dym_probe_meta"]["ok"] is True
        assert out["dym_available_codes"] == ["srtwc282"], (
            "baseline detailed-mode summing regressed: only SRTWC282 has qty > 0"
        )


# --------------------------------------------------------------------------- #
# AC 2: compact mode - available iff "Total" > 0, per-location fields ignored.
# --------------------------------------------------------------------------- #


class TestCompactModeUsesTotalField:
    def _item(self):
        return _base_item(
            stock_visibility={
                "mode": "compact",
                "warehouse_codes": None,
                "hide_zero_locations": True,
                "source": "contact",
            },
            result_type="stock_compact",
            answers=[
                {
                    "title": "SRTWC282",
                    "fields": [
                        {"label": "Product Code", "value": "SRTWC282"},
                        {"label": "Total", "value": 6},
                        {"label": "WH3", "value": 6},
                    ],
                },
                {
                    "title": "SRTWC286-SH-P",
                    "fields": [
                        {"label": "Product Code", "value": "SRTWC286-SH-P"},
                        {"label": "Total", "value": 0},
                    ],
                },
            ],
        )

    def test_total_field_drives_availability_not_location_rows(self) -> None:
        out = dym_annotate(self._item())
        assert out["dym_probe_meta"]["ok"] is True
        assert out["dym_available_codes"] == ["srtwc282"], (
            "compact mode must read the 'Total' field - SRTWC282 has Total 6, "
            "SRTWC286-SH-P has Total 0 and must not be marked available"
        )

    def test_mode_is_recorded_on_meta(self) -> None:
        out = dym_annotate(self._item())
        assert out["dym_probe_meta"]["mode"] == "compact"

    def test_compact_fix_reaches_the_partial_lane_wrapper_too(self) -> None:
        out = dym_annotate_partial(self._item())
        assert out["dym_available_codes"] == ["srtwc282"], (
            "the results-lane annotator copy (dym_annotate_partial / sub_answer.py) must "
            "get the same compact-mode fix as the miss-lane one"
        )

    def test_twin_codes_across_companies_accumulate_not_overwrite(self) -> None:
        """A Sorento and a Mocha twin share the same code and carry no Company field to
        tell them apart in a compact row - a zero-stock twin must not erase a stocked one.
        """
        item = _base_item(
            stock_visibility={
                "mode": "compact",
                "warehouse_codes": None,
                "hide_zero_locations": True,
                "source": "contact",
            },
            result_type="stock_compact",
            answers=[
                {
                    "title": "MWC-SC08B",
                    "fields": [
                        {"label": "Product Code", "value": "MWC-SC08B"},
                        {"label": "Total", "value": 6},
                    ],
                },
                {
                    "title": "MWC-SC08B",
                    "fields": [
                        {"label": "Product Code", "value": "MWC-SC08B"},
                        {"label": "Total", "value": 0},
                    ],
                },
            ],
        )
        out = dym_annotate(item)
        assert out["dym_probe_meta"]["ok"] is True
        assert out["dym_available_codes"] == ["mwc-sc08b"], (
            "the zero-stock twin's Total must not overwrite the stocked twin's Total - "
            "the two rows accumulate, like the detailed arm's per-code sum"
        )


# --------------------------------------------------------------------------- #
# AC 3: availability mode ALWAYS fails open. The did-you-mean probe never sends
# `requested_qty` (`entity_ids_transformer` in fetch.py emits no such key), so the
# backend answers `needs_quantity: True, available: None` on every row today - and even
# if `requested_qty` ever arrived, `available` is a QUANTITY VERDICT
# (`on_hand >= requested_qty`), not "has stock details", so trusting it would render a
# false "no" on a code that has some stock, just less than the requested amount.
# --------------------------------------------------------------------------- #


class TestAvailabilityModeAlwaysFailsOpen:
    def _item(self, answers):
        return _base_item(
            stock_visibility={
                "mode": "availability",
                "warehouse_codes": None,
                "hide_zero_locations": True,
                "source": "contact",
            },
            result_type="stock_availability",
            answers=answers,
        )

    def test_available_true_still_fails_open(self) -> None:
        item = self._item(
            [
                {"title": "SRTWC282", "fields": [], "needs_quantity": False, "available": True},
                {"title": "SRTWC286-SH-P", "fields": [], "needs_quantity": False, "available": False},
            ]
        )
        out = dym_annotate(item)
        assert out["dym_probe_meta"]["ok"] is False
        assert out["dym_probe_meta"]["reason"] == "availability_unknown"
        assert out["dym_available_codes"] == []
        assert out["dym_probe_meta"]["mode"] == "availability"

    def test_needs_quantity_still_fails_open(self) -> None:
        item = self._item(
            [
                {"title": "SRTWC282", "fields": [], "needs_quantity": False, "available": True},
                {"title": "SRTWC286-SH-P", "fields": [], "needs_quantity": True, "available": None},
            ]
        )
        out = dym_annotate(item)
        assert out["dym_probe_meta"]["ok"] is False
        assert out["dym_probe_meta"]["reason"] == "availability_unknown"
        assert out["dym_available_codes"] == []
        assert out["dym_probe_meta"]["mode"] == "availability"

    def test_no_flags_at_all_still_fails_open(self) -> None:
        item = self._item(
            [
                {"title": "SRTWC282", "fields": []},
            ]
        )
        out = dym_annotate(item)
        assert out["dym_probe_meta"]["ok"] is False
        assert out["dym_probe_meta"]["reason"] == "availability_unknown"
        assert out["dym_available_codes"] == []
        assert out["dym_probe_meta"]["mode"] == "availability"


# --------------------------------------------------------------------------- #
# AC 4: an unrecognised mode string fails open rather than silently defaulting
# to the detailed-mode summing (which would misread compact/availability rows).
# --------------------------------------------------------------------------- #


class TestUnknownStockModeFailsOpen:
    def test_unknown_mode_string_fails_open_with_reason(self) -> None:
        item = _base_item(
            stock_visibility={"mode": "banded"},
            answers=[
                {
                    "title": "SRTWC282",
                    "fields": [
                        {"label": "Product Code", "value": "SRTWC282"},
                        {"label": "Quantity On Hand", "value": 6},
                    ],
                },
            ],
        )
        out = dym_annotate(item)
        assert out["dym_probe_meta"]["ok"] is False
        assert out["dym_probe_meta"]["reason"] == "unknown_stock_mode"
        assert out["dym_available_codes"] == []
        assert out["dym_probe_meta"]["mode"] == "banded"
