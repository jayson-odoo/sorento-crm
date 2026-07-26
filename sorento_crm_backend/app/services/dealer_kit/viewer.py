"""Who is looking, and what they may see.

The saved page document holds no prices and no access decisions (AC-G1) - only
bindings. Everything price-shaped is decided HERE, at read time, from the viewer
in front of us. That is what lets one published document serve staff, a dealer
and a consumer without three copies drifting apart.

The rule that matters is that a price a viewer may not see never reaches them.
Not hidden with CSS, not sent-and-ignored: absent from the response (AC-G7).
A field that is not in the payload cannot leak by inspecting it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewerContext:
    """Resolved once per render and passed down.

    ``show_invoice_price`` is the DOCUMENT's toggle and ``may_see_invoice_price``
    is the VIEWER's entitlement. They are ANDed, and they are separate fields on
    purpose: collapsing them into one boolean at the call site is exactly the
    mistake that lets someone turn a page toggle on and expose an internal price
    to a consumer (AC-G6).
    """

    is_staff: bool = False
    access_codes: frozenset[str] = frozenset()
    show_invoice_price: bool = False

    @property
    def may_see_invoice_price(self) -> bool:
        # Staff only. A dealer negotiating on price must not read the figure the
        # invoice will be raised at, and a consumer certainly must not.
        return self.is_staff

    @property
    def invoice_price_visible(self) -> bool:
        return self.show_invoice_price and self.may_see_invoice_price


ANONYMOUS = ViewerContext()
