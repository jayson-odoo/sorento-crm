"""SPO import: missing packing list is a warning, not a blocking error.

Both the test (validate) and the actual import classify a row whose inbound
shipment / packing list can't be found as a warning so the uploader is warned
rather than blocked, while genuine data problems stay errors.
"""
from __future__ import annotations

from app.tasks.import_tasks import partition_spo_skip_reasons


def test_missing_packing_list_is_a_warning():
    skipped = [
        {"row": 3, "reason": "Packing list not found for container: MSKU123"},
    ]
    errors, warnings = partition_spo_skip_reasons(skipped)
    assert errors == []
    assert warnings == ["Row 3: Packing list not found for container: MSKU123"]


def test_data_problems_stay_errors():
    skipped = [
        {"row": 2, "reason": "Product not found: ABC"},
        {"row": 4, "reason": "Warehouse not found: KL"},
        {"row": 5, "reason": "Invalid or zero Qty"},
    ]
    errors, warnings = partition_spo_skip_reasons(skipped)
    assert warnings == []
    assert len(errors) == 3


def test_mixed_skips_split_correctly():
    skipped = [
        {"row": 1, "reason": "Packing list not found for container: A1"},
        {"row": 2, "reason": "Product not found: XYZ"},
        {"row": 3, "reason": "Packing list not found for container: B2"},
    ]
    errors, warnings = partition_spo_skip_reasons(skipped)
    assert len(warnings) == 2
    assert errors == ["Row 2: Product not found: XYZ"]
