"""Anchored inserts into the chatbot parser prompt (lane SALES-TARGET-CHAT).

The section text lives once, here, so it can be re-applied to whatever text the production
label moves to. `insert_sales_target` returns None when the anchor is not there exactly once
or the section is already present.
"""
from __future__ import annotations

SALES_TARGET_ANCHOR = '== SALES REPORT: order_status "sales_report", domain_hint "order" =='

SALES_TARGET_SECTION = """== SALES TARGET: order_status "sales_target", domain_hint "order" ==
A question about a SALES TARGET - what has been achieved against a target, how far it is
to the target or to the next tier of it, which tier or rebate / incentive rate has been
reached - is order_status "sales_target", domain_hint "order", intent_hint "check_order".
The target words decide it, in any language: "target", "achievement", "achieved",
"next tier", "rebate tier", "incentive tier", "hit the target", "sasaran", "pencapaian",
"capai sasaran", "目标", "达标", "完成率", "返利". It is a DIFFERENT ask from the sales
ranking, sales report and sales analysis asks around it, which carry no target word; an ask
with no target word is never "sales_target". "tier" here is a level of a sales target or
rebate, never an access level.
  - "how is my target this quarter" -> order_status "sales_target", self_reference
    true, date_filter_start / date_filter_end the current quarter's first and last day,
    entities []
  - "did we hit the Q3 target?" -> order_status "sales_target", self_reference true,
    date_filter_start / date_filter_end the first and last day of Q3 of the current year
  - "how far to the next rebate tier" -> order_status "sales_target", entities []
  - "BKIN ELECTRICAL target achievement" -> order_status "sales_target", entities
    [BKIN ELECTRICAL as customer]
  - "my dealers' targets" -> order_status "sales_target", self_reference true,
    entities []
  - "sasaran jualan saya bulan ini" -> order_status "sales_target", self_reference
    true, date_filter_start / date_filter_end the current month
  - "我这个季度的销售目标完成了多少" -> order_status "sales_target", self_reference true,
    date_filter_start / date_filter_end the current quarter
A SALES TARGET ask leaves sales_channel and group_by null and requested_attributes [].

"""


def insert_sales_target(text: str) -> str | None:
    if SALES_TARGET_SECTION.split("\n", 1)[0] in text:
        return None
    if text.count(SALES_TARGET_ANCHOR) != 1:
        return None
    return text.replace(SALES_TARGET_ANCHOR, SALES_TARGET_SECTION + SALES_TARGET_ANCHOR, 1)
