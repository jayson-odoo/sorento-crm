"""What `class_of` calls Project and what it calls Retail (front planning 5.2, AC-E01).

`sales_orders.demand_class` is the semantic owner of the Project/Retail split that the whole
front plan is built on, and every writer of that column resolves through this one function:
`outstanding_import_service._classify_demand` for the outstanding-order and AutoCount
uploads, and `project_order_inquiry_import_service` for the sheet-created orders. So the
substring rule below is not an implementation detail of one importer - it is the definition
of the channel, and a change to it silently re-classifies both feeds at once.

The precedence AROUND the mapper (stored order type, then stated order type, then the
customer's market segment, then the sales agent's class) is pinned separately, in
`test_outstanding_import_demand_class.py` and `test_outstanding_import_agent.py`. Pinned
HERE is only the mapping itself, without a database, because it is pure.

Three facts, and the third is the one that is easy to lose:

* anything containing `project`, `projects` or `contract` is Project, matched as a
  SUBSTRING because the real values are typed by people (`subcontractor` counts, and so
  does `Project Sales`);
* every other STATED value is Retail;
* nothing stated is `None`, which is NOT Retail. "This is not a project" and "nobody said"
  look identical in a spreadsheet column and mean opposite things, so only the first may be
  written and the second is reported as a classification exception.
"""
from __future__ import annotations

import pytest

from app.services.scm.demand_class import PROJECT, class_of

RETAIL = "retail"


@pytest.mark.parametrize(
    "stated",
    ["project", "projects", "contract", "subcontractor", "Project Sales", "PROJECTS"],
)
def test_a_value_naming_project_work_maps_to_project(stated):
    """`subcontractor` contains `contract`, and that is deliberate, not an accident."""
    assert class_of(stated) == PROJECT


@pytest.mark.parametrize("stated", ["dealer", "retail", "end user", "wholesale"])
def test_every_other_stated_value_maps_to_retail(stated):
    assert class_of(stated) == RETAIL


@pytest.mark.parametrize("unstated", [None, "", "   "])
def test_nothing_stated_maps_to_nothing(unstated):
    """None is load-bearing: defaulting it to retail is the failure the column exists for.

    A project order quietly stamped retail under-prioritises itself invisibly, and the wrong
    answer is stable, so no later upload surfaces it either.
    """
    assert class_of(unstated) is None
