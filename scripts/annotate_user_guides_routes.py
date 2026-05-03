"""Wrap menu / page mentions in user guides with markdown links to the
actual CRM frontend routes.

The point: the AI assistant pipes guide markdown straight back to the user.
If the guide reads `**Resource Management → Files**`, the FE renders only
text. If it reads `[**Resource Management → Files**](/resource-management/attachment-directories)`,
the user gets a clickable shortcut to the page.

This script is idempotent — running it twice is a no-op (skips any mention
that's already inside a markdown link).

Run:
    python scripts/annotate_user_guides_routes.py

Then push to Outline:
    python scripts/sync_user_guides_outline.py push
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDES_DIR = REPO_ROOT / "docs" / "user-guides"

# Order matters: longer, more-specific paths first so they match before the
# shorter parents (e.g. "Resource Management → Files" before "Resource Management").
ROUTE_MAP: list[tuple[str, str]] = [
    # Resource Management
    ("Resource Management → Files", "/resource-management/attachment-directories"),
    ("Resource Management → Attachment Types", "/resource-management/attachment-types"),
    ("Resource Management → Trash", "/resource-management/trash"),
    # Procurement
    ("Procurement → Stock Inquiries", "/procurement-management/stock-inquiries"),
    ("Procurement → Purchase Requests", "/procurement-management/purchase-requests"),
    ("Procurement → Sponsorship Forms", "/procurement-management/sponsorship-forms"),
    ("Procurement → SPO Allocations", "/procurement-management/spo-allocations"),
    ("Procurement → Packing Lists", "/procurement-management/packing-lists"),
    ("Procurement → GRN", "/procurement-management/grn"),
    # Master Data
    ("Master Data Management → Products", "/master-data-management/products"),
    # Delivery Order Management
    ("Delivery Order Management → Delivery Orders", "/order-management/orders"),
    # Inventory
    ("Inventory Management → Warehouses", "/inventory-management/warehouses"),
    ("Inventory Management → Stock", "/inventory-management/stock"),
    # Marketing
    ("Marketing Management → Promotion Products", "/marketing-management/promotion-products"),
    ("Marketing Management → Promotions", "/marketing-management/promotions"),
    # Complaints
    ("Complaint Management → Complaints", "/complaint-management/complaints"),
    # System
    ("System Management → Integration Logs", "/system-management/integration-logs"),
    ("System Management → Import Jobs", "/system-management/import-jobs"),
    # User management
    ("User Management → Contacts", "/user-management/contacts"),
]

# Skip files that don't ship to end users.
EXCLUDE = {"SYNC.md", ".outline-sync.json"}


def annotate(text: str) -> tuple[str, int]:
    """Wrap `**<label>**` mentions of known menu paths with a markdown link
    pointing at the route. Skips mentions that are already inside a link.
    """
    replaced = 0
    for label, route in ROUTE_MAP:
        # Match `**<label>**` not already inside `[**<label>**](...)`.
        # Negative-lookbehind: not preceded by `](`. Negative-lookahead: not
        # followed by `](`. We also skip when the bold marker is wrapped in
        # backticks (code) — uncommon for menu paths.
        pattern = re.compile(
            r"(?<!\]\()(?<!`)\*\*"
            + re.escape(label)
            + r"\*\*(?!\]\()"
        )
        new_link = f"[**{label}**]({route})"
        new_text, count = pattern.subn(new_link, text)
        if count:
            replaced += count
            text = new_text
    return text, replaced


def main() -> int:
    total_files = 0
    total_subs = 0
    for md in sorted(GUIDES_DIR.rglob("*.md")):
        rel = md.relative_to(GUIDES_DIR)
        if str(rel) in EXCLUDE:
            continue
        original = md.read_text()
        new_text, subs = annotate(original)
        if subs:
            md.write_text(new_text)
            total_files += 1
            total_subs += subs
            print(f"  {rel}  ({subs} subs)")
    print(f"Done. Annotated {total_subs} mention(s) across {total_files} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
