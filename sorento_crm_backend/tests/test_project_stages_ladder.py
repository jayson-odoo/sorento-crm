"""PROJECT-STAGES-SAMPLE: the ladder migration, exercised on a prod-shaped graph.

UAC: documentation/plans/projects/project-stages-sample-acceptance-criteria.md.
CI's seed has quoted/tendering instead of the sample/negotiation rungs, so every test here
builds the prod-shaped default project graph itself, inside a rolled-back blank schema.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.projects import Project
from app.models.status import Status, StatusTransition
from app.services import project_po_service, project_seed_service, status_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = _BACKEND / "alembic" / "versions" / "stg_0001_project_ladder_edges.py"

# key, label, sort_order, is_initial, is_terminal, win_probability, stale_after_days
_RUNGS = [
    ("identified", "Identified", 0, False, False, 5, 90),
    ("registered", "Registered", 1, True, False, 10, 60),
    ("specified", "Spec In", 2, False, False, 25, 45),
    ("sample_submission", "Sample Submission", 4, False, False, 40, 30),
    ("final_negotiation", "Final Negotiation", 5, False, False, None, None),
    ("sponsorship_form", "Sponsorship Form", 6, False, False, None, None),
    ("po_received", "PO Received", 7, False, True, 100, None),
    ("lost", "Lost", 8, False, True, 0, None),
    ("dormant", "Dormant", 9, False, True, 0, None),
]

_OLD_EDGES = [
    ("identified", "registered", "Register with developer"),
    ("identified", "dormant", "Mark dormant"),
    ("identified", "lost", "Mark lost"),
    ("identified", "po_received", "PO received"),
    ("registered", "specified", "Spec In"),
    ("registered", "identified", "Back to identified"),
    ("registered", "lost", "Mark lost"),
    ("registered", "dormant", "Mark dormant"),
    ("registered", "po_received", "PO received"),
    ("specified", "dormant", "Mark dormant"),
    ("specified", "po_received", "PO received"),
    ("specified", "registered", "Back to registered"),
    ("specified", "lost", "Mark lost"),
    ("sample_submission", "dormant", "Mark dormant"),
    ("sample_submission", "lost", "Mark lost"),
    ("sample_submission", "po_received", "PO received"),
]

_NEW_EDGES = [
    ("specified", "sample_submission", "Sample submitted"),
    ("sample_submission", "final_negotiation", "Final negotiation"),
    ("final_negotiation", "sponsorship_form", "Sponsorship"),
    ("sponsorship_form", "po_received", "PO received"),
    ("final_negotiation", "po_received", "PO received"),
    ("sample_submission", "specified", "Back to Spec In"),
    ("final_negotiation", "sample_submission", "Back to sample submission"),
    ("sponsorship_form", "final_negotiation", "Back to final negotiation"),
    ("final_negotiation", "lost", "Mark lost"),
    ("final_negotiation", "dormant", "Mark dormant"),
    ("sponsorship_form", "lost", "Mark lost"),
    ("sponsorship_form", "dormant", "Mark dormant"),
]


def _load():
    spec = importlib.util.spec_from_file_location("migration_stg_0001", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, step: str) -> None:
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        getattr(_load(), step)()


def _prod_graph(db) -> dict:
    rungs = {}
    for key, label, order, initial, terminal, win, stale in _RUNGS:
        row = Status(
            id=str(uuid.uuid4()),
            entity_type="project",
            scope_id=None,
            key=key,
            label=label,
            sort_order=order,
            is_initial=initial,
            is_terminal=terminal,
            win_probability=win,
            stale_after_days=stale,
        )
        db.add(row)
        rungs[key] = row
    db.flush()
    for src, dst, label in _OLD_EDGES:
        _add_edge(db, rungs[src], rungs[dst], label)
    return rungs


def _add_edge(db, source, target, label) -> None:
    db.add(
        StatusTransition(
            id=str(uuid.uuid4()),
            entity_type="project",
            scope_id=None,
            from_status_id=source.id,
            to_status_id=target.id,
            label=label,
            trigger_mode="manual",
        )
    )
    db.flush()


def _edge_triples(db) -> list:
    rows = db.execute(
        text(
            "SELECT f.key, t.key, e.label, e.trigger_mode FROM status_transitions e "
            "JOIN statuses f ON f.id = e.from_status_id "
            "JOIN statuses t ON t.id = e.to_status_id "
            "WHERE e.entity_type = 'project' AND e.scope_id IS NULL "
            "AND f.key IN :keys"
        ).bindparams(__import__("sqlalchemy").bindparam("keys", expanding=True)),
        {"keys": [r[0] for r in _RUNGS]},
    ).all()
    return sorted((a, b, c) for a, b, c, _ in rows)


def _rung_snapshot(db) -> list:
    rows = db.execute(
        text(
            "SELECT key, label, sort_order, is_initial, is_terminal, win_probability, "
            "stale_after_days FROM statuses WHERE entity_type = 'project' AND scope_id IS NULL "
            "AND key IN :keys ORDER BY key"
        ).bindparams(__import__("sqlalchemy").bindparam("keys", expanding=True)),
        {"keys": [r[0] for r in _RUNGS]},
    ).all()
    return [tuple(r) for r in rows]


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def test_ps01_adds_exactly_the_twelve_labelled_edges(db):
    """AC-PS-01"""
    _prod_graph(db)
    _run(db, "upgrade")
    assert _edge_triples(db) == sorted(_OLD_EDGES + _NEW_EDGES)


def test_ps02_idempotent_and_keeps_an_admins_own_edge(db):
    """AC-PS-02"""
    rungs = _prod_graph(db)
    _add_edge(db, rungs["specified"], rungs["sample_submission"], "Send sample")
    _run(db, "upgrade")
    _run(db, "upgrade")
    triples = _edge_triples(db)
    assert triples.count(("specified", "sample_submission", "Send sample")) == 1
    assert [t for t in triples if t[:2] == ("specified", "sample_submission")] == [
        ("specified", "sample_submission", "Send sample")
    ]
    expected = sorted(
        _OLD_EDGES
        + [e for e in _NEW_EDGES if e[:2] != ("specified", "sample_submission")]
        + [("specified", "sample_submission", "Send sample")]
    )
    assert triples == expected


def test_ps03_code_seed_graph_gets_nothing_and_does_not_raise(db):
    """AC-PS-03: quoted/tendering seed has none of the new rungs."""
    project_seed_service.seed_default_funnel(db)
    before = db.execute(text("SELECT count(*) FROM status_transitions")).scalar()
    _run(db, "upgrade")
    after = db.execute(text("SELECT count(*) FROM status_transitions")).scalar()
    assert after == before


def test_ps04_ps05_old_edges_and_rungs_unchanged(db):
    """AC-PS-04, AC-PS-05"""
    _prod_graph(db)
    rungs_before = _rung_snapshot(db)
    _run(db, "upgrade")
    assert _rung_snapshot(db) == rungs_before
    triples = _edge_triples(db)
    for edge in _OLD_EDGES:
        assert edge in triples


def test_ps06_downgrade_removes_only_its_own_edges(db):
    """AC-PS-06"""
    rungs = _prod_graph(db)
    _add_edge(db, rungs["final_negotiation"], rungs["lost"], "Closed lost")
    _run(db, "upgrade")
    _run(db, "downgrade")
    assert _edge_triples(db) == sorted(
        _OLD_EDGES + [("final_negotiation", "lost", "Closed lost")]
    )


@pytest.mark.parametrize("label,survives", [("Back to Spec In", False), ("Rework spec", True)])
def test_ps06b_downgrade_matches_the_exact_label(db, label, survives):
    """AC-PS-06: an edge on a migration from/to pair goes only when its label is exact.

    The edge key is unique per from/to pair, so the two labels run as separate cases.
    """
    rungs = _prod_graph(db)
    _add_edge(db, rungs["sample_submission"], rungs["specified"], label)
    _run(db, "upgrade")
    _run(db, "downgrade")
    present = ("sample_submission", "specified", label) in _edge_triples(db)
    assert present is survives


def test_ps15_no_forward_skips_after_upgrade(db):
    """AC-PS-15"""
    rungs = _prod_graph(db)
    _run(db, "upgrade")
    for target in ("final_negotiation", "sponsorship_form"):
        with pytest.raises(AppException) as exc:
            status_service.assert_transition_allowed(
                db, "project", rungs["specified"].id, rungs[target].id
            )
        assert exc.value.status_code == 422
    edge = status_service.assert_transition_allowed(
        db, "project", rungs["sample_submission"].id, rungs["final_negotiation"].id
    )
    assert edge is not None


def _project_at(db, status: Status) -> Project:
    company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
    owner = str(uuid.uuid4())
    from app.models.user import User

    db.add(User(id=owner, email=f"{owner}@zzt.test", name="zzt-stg owner"))
    db.flush()
    project = Project(
        id=str(uuid.uuid4()),
        company_id=company_id,
        project_code=f"zzt-stg-{uuid.uuid4().hex[:6]}",
        title="Stages ladder project",
        normalised_title="stages ladder project",
        owner_user_id=owner,
        status_id=status.id,
    )
    db.add(project)
    db.flush()
    return project


@pytest.mark.parametrize("start", ["final_negotiation", "sponsorship_form"])
def test_ps30_first_po_moves_from_late_rungs(db, start):
    """AC-PS-30: no edge before the migration (False), moved after it (True)."""
    rungs = _prod_graph(db)
    project = _project_at(db, rungs[start])
    _run(db, "upgrade")
    assert project_po_service._advance_to_po_received(db, project) is True
    assert project.status_id == rungs["po_received"].id


def _status_key_window(path: pathlib.Path, marker: str) -> str:
    src = path.read_text()
    start = src.index(marker)
    window = src[start : start + 700]
    cut = re.search(r"(An unknown key|Unknown keys)", window)
    window = window[: cut.start()] if cut else window
    return re.sub(r"[\"'\s]+", " ", window)


@pytest.mark.parametrize(
    "path,marker",
    [
        (
            _BACKEND.parent / "sorento_crm_mcp" / "sorento_crm_mcp" / "catalog.py",
            "`status_key` -- funnel rung",
        ),
        (_BACKEND / "app" / "api" / "v1" / "projects" / "projects.py", "Funnel rung by stable KEY"),
        (
            _BACKEND / "app" / "services" / "analytics_connector" / "reused_tools.py",
            "`status_key` -- funnel rung",
        ),
    ],
)
def test_ps40_status_key_text_names_the_new_rungs(path, marker):
    """AC-PS-40"""
    window = _status_key_window(path, marker)
    for key in ("sample_submission", "final_negotiation", "sponsorship_form"):
        assert key in window, window
    assert "quoted" not in window and "tendering" not in window, window


_MCP_CATALOG = _BACKEND.parent / "sorento_crm_mcp" / "sorento_crm_mcp" / "catalog.py"
_REUSED = _BACKEND / "app" / "services" / "analytics_connector" / "reused_tools.py"


def _projects_list_description(path: pathlib.Path, start_marker: str, end_marker: str) -> str:
    src = path.read_text()
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return re.sub(r"[\"'\s]+", " ", src[start:end])


def _both_descriptions() -> list:
    return [
        _projects_list_description(
            _MCP_CATALOG, '"crm_projects_list",\n', '"crm_project_detail",'
        ),
        _projects_list_description(
            _REUSED,
            '"name": \'crm_projects_list\'',
            '"name": \'crm_resource_attachments_catalogue\'',
        ),
    ]


def test_ps40_whole_projects_list_description_has_no_retired_stage_words():
    """AC-PS-40: no 'quoted' / 'tendering' anywhere in the tool description."""
    for window in _both_descriptions():
        assert "tendering" not in window, window
        assert "quoted" not in window, window


def test_ps41_only_critical_is_not_called_the_final_negotiation_flag():
    """AC-PS-41"""
    for window in _both_descriptions():
        line = window[window.index("only_critical=true") :][:160]
        assert "the Final Negotiation flag" not in line, line
        assert "critical" in line.lower(), line
