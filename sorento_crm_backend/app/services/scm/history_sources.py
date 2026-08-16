"""Which `source_system` stamps mean "this row is imported HISTORY".

A three-line module because the answer has to be readable from two places that must not
import each other's write paths: the feed that WRITES history (`po_history_service`) and the
feed that must never touch it (`outstanding_import_service`, whose revive path lifts a closed
line back to open).

That second reader is the reason this exists at all. History is written closed AND fully
received so `scm.on_order_v` and `scm.po_ordered_v` cannot count it - but "closed" is a state
another importer is allowed to reverse, and the outstanding-PO extract reverses it by design
(a line that comes back is the same line, and the receipt already booked against it belongs
to it). Told apart by the stamp, the two feeds can share `purchase_orders` without either one
having to know what the other's file looks like.
"""
from __future__ import annotations

#: Purchase-order family (`202301-S0001`), both export shapes.
PO_HISTORY_SOURCE = "scm_po_history"
#: Shipping-order family (`SPO-2023/01-0001`), written by the same channel.
SPO_HISTORY_SOURCE = "scm_spo_history"
#: The sales book (`so_history_service`). Listed for the same reason, on the same shared
#: table: the outstanding SO extract writes `sales_order_lines` too.
SO_HISTORY_SOURCE = "scm_so_history"

#: Every stamp that means history. Anything matching this was written by a feed that states
#: what ALREADY happened, so no other importer may re-open it, re-quantify it or adopt it.
HISTORY_SOURCE_SYSTEMS = (PO_HISTORY_SOURCE, SPO_HISTORY_SOURCE, SO_HISTORY_SOURCE)
