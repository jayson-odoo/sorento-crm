"""Dealer targets import, accent folding (lane SALES-TARGET-DEALER, crew ruling 20 Oct, Mocha 79-81).

An accented letter in a dealer name is the same letter without its accent ("DÉCOR" = "DECOR"):
`dealer_key` folds accents (NFKD, combining marks dropped) before it compares. This is the owner's
16 Oct rule "exact normalised name + account label auto-maps", not fuzzy matching: nothing else is
loosened, and a different letter is still a different name. Masked names.
"""
from __future__ import annotations

from .test_dealer_targets_import_gate5 import _customer, _dry_run
from .test_sales_targets_s1 import api, world  # noqa: F401  (fixtures)


def test_an_accented_letter_is_the_same_letter():
    from app.services.sales.dealer_target_import import dealer_key

    assert dealer_key("CAFÉ DÉCOR SDN BHD") == dealer_key("CAFE DECOR SDN BHD") == "CAFE DECOR"
    assert dealer_key("Café Décor Sdn Bhd [A/C I]") == "CAFE DECOR"
    assert dealer_key("NUÑEZ & SÖHNE ENTERPRISES") == "NUNEZ SOHNE ENTERPRISE"


def test_a_different_letter_is_still_a_different_name():
    from app.services.sales.dealer_target_import import dealer_key

    assert dealer_key("CAFÉ DÉCOR") != dealer_key("CAFE DEKOR")
    assert dealer_key("CAFÉ DÉCOR") != dealer_key("CAFE DECORS")


def test_a_file_name_with_accents_auto_maps_to_the_plain_ledger(api):
    client, db, company_id = api
    plain = _customer(db, company_id, "CAFE DECOR SDN BHD [A/C I]", 1)
    row = _dry_run(client, db, "Café Décor Sdn Bhd", "A/C I")
    assert row["match"] == "auto" and row["customer"] == plain.customer_name, row


def test_a_plain_file_name_auto_maps_to_the_accented_ledger(api):
    client, db, company_id = api
    accented = _customer(db, company_id, "CAFÉ DÉCOR SDN BHD [A/C I]", 1)
    row = _dry_run(client, db, "CAFE DECOR SDN BHD", "A/C I")
    assert row["match"] == "auto" and row["customer"] == accented.customer_name, row


def test_the_ledger_written_with_the_same_accents_wins_the_tie(api):
    client, db, company_id = api
    _customer(db, company_id, "RENE TILES SDN BHD", 1)
    accented = _customer(db, company_id, "RENÉ TILES SDN BHD", 1)
    row = _dry_run(client, db, "René Tiles Sdn Bhd", "A/C I")
    assert row["match"] == "auto" and row["customer"] == accented.customer_name, row


def test_a_misspelt_name_is_not_matched(api):
    client, db, company_id = api
    _customer(db, company_id, "CAFÉ DÉCOR SDN BHD [A/C I]", 1)
    row = _dry_run(client, db, "CAFE DEKOR SDN BHD", "A/C I")
    assert row["match"] != "auto", row
    assert row["reason"].startswith("no customer has this name"), row["reason"]
