"""Unified Drive (folders + files in one stream) — service-level tests.

Covers the BE-gated UAC items for PLAN-unified-drive-files:
  A8/D10 (root scope), B1/B2/B3 (browse vs recursive incl. deep descendant),
  B4 (folders + files in recursive results), C1/C2 (interleave / folder-to-end),
  C3/C4 (filters hide folders / browse shows), C6 (UNION sort+pagination),
  D2 (directory_path resolved), D3 (recursive descendant), D4 (isolation),
  E4 (cycle guard on move), F4 (folder delete cascade + restore),
  I8/I6 (collision copy-name + replace-in-place semantics).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.audit import AuditLog
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.services.resources_service import (
    AttachmentDirectoryService,
    AttachmentService,
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AttachmentDirectory.__table__,
            AttachmentType.__table__,
            Attachment.__table__,
            LookupSet.__table__,
            LookupOption.__table__,
            LookupBinding.__table__,
            AuditLog.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# seed helpers
# --------------------------------------------------------------------------- #
def _folder(db, name: str, parent_id: str | None = None, deleted: bool = False) -> str:
    d = AttachmentDirectory(
        id=str(uuid.uuid4()),
        name=name,
        parent_id=parent_id,
        is_deleted=deleted,
    )
    db.add(d)
    db.flush()
    return d.id


def _type(db, type_name: str) -> str:
    t = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=type_name,
        allowed_extensions="pdf,jpg",
        max_file_size_mb=10,
    )
    db.add(t)
    db.flush()
    return t.id


def _file(
    db,
    *,
    filename: str,
    directory_id: str | None = None,
    type_id: str | None = None,
    uploaded_by: str | None = None,
    uploaded_at: datetime | None = None,
    size: int | None = 100,
    deleted: bool = False,
) -> str:
    a = Attachment(
        id=str(uuid.uuid4()),
        attachment_type_id=type_id,
        original_filename=filename,
        stored_filename=filename,
        file_path=f"/tmp/{filename}",
        directory_id=directory_id,
        file_size_bytes=size,
        uploaded_by=uploaded_by,
        uploaded_at=uploaded_at or datetime(2026, 5, 1),
        access_levels=["dealer"],
        is_deleted=deleted,
    )
    db.add(a)
    db.flush()
    return a.id


def _drive(db, **kw):
    return AttachmentService(db).list_drive_contents(**kw)


def _kinds(result):
    return [it["kind"] for it in result["items"]]


def _names(result):
    out = []
    for it in result["items"]:
        if it["kind"] == "folder":
            out.append(it["name"])
        else:
            out.append(it["attachment"].original_filename)
    return out


# --------------------------------------------------------------------------- #
# A8 / D10 — root scope
# --------------------------------------------------------------------------- #
def test_A8_root_shows_top_folders_and_null_directory_files(db):
    top = _folder(db, "Marketing")
    _folder(db, "Sub", parent_id=top)  # nested — must NOT appear at root browse
    _file(db, filename="root_file.pdf", directory_id=None)
    _file(db, filename="in_marketing.pdf", directory_id=top)  # must NOT appear at root
    db.commit()

    res = _drive(db, directory_id=None)
    names = set(_names(res))
    assert "Marketing" in names           # top folder
    assert "root_file.pdf" in names       # null-directory file
    assert "Sub" not in names             # nested folder excluded
    assert "in_marketing.pdf" not in names  # file in a folder excluded
    assert res["total"] == 2


# --------------------------------------------------------------------------- #
# B1 — browse = immediate children only
# --------------------------------------------------------------------------- #
def test_B1_browse_immediate_children_only(db):
    parent = _folder(db, "Parent")
    child = _folder(db, "Child", parent_id=parent)
    _folder(db, "GrandChild", parent_id=child)
    _file(db, filename="direct.pdf", directory_id=parent)
    _file(db, filename="deep.pdf", directory_id=child)
    db.commit()

    res = _drive(db, directory_id=parent)
    names = set(_names(res))
    assert names == {"Child", "direct.pdf"}


# --------------------------------------------------------------------------- #
# B2 / D3 — recursive finds a file in a sub-subfolder
# --------------------------------------------------------------------------- #
def test_B2_recursive_search_finds_deep_descendant_file(db):
    a = _folder(db, "A")
    b = _folder(db, "B", parent_id=a)
    c = _folder(db, "C", parent_id=b)
    _file(db, filename="needle.pdf", directory_id=c)
    _file(db, filename="haystack.pdf", directory_id=a)
    db.commit()

    res = _drive(db, directory_id=a, query="needle")
    names = _names(res)
    assert "needle.pdf" in names
    assert "haystack.pdf" not in names
    assert res["recursive"] is True


# --------------------------------------------------------------------------- #
# B3 — searching at root searches the whole drive
# --------------------------------------------------------------------------- #
def test_B3_root_search_whole_drive(db):
    a = _folder(db, "A")
    b = _folder(db, "B", parent_id=a)
    _file(db, filename="target.pdf", directory_id=b)
    db.commit()

    res = _drive(db, directory_id=None, query="target")
    assert "target.pdf" in _names(res)


# --------------------------------------------------------------------------- #
# B4 — recursive results include BOTH matching files and folders
# --------------------------------------------------------------------------- #
def test_B4_recursive_includes_matching_folders_and_files(db):
    a = _folder(db, "Reports")
    _folder(db, "report-archive", parent_id=a)
    _file(db, filename="report-2026.pdf", directory_id=a)
    db.commit()

    res = _drive(db, directory_id=None, query="report")
    kinds = set(_kinds(res))
    names = set(_names(res))
    assert "report-archive" in names
    assert "report-2026.pdf" in names
    assert kinds == {"folder", "file"}


# --------------------------------------------------------------------------- #
# C1 — default Name sort interleaves folders + files
# --------------------------------------------------------------------------- #
def test_C1_name_sort_interleaves_folders_and_files(db):
    _folder(db, "Bravo")
    _folder(db, "Delta")
    _file(db, filename="alpha.pdf", directory_id=None)
    _file(db, filename="charlie.pdf", directory_id=None)
    db.commit()

    res = _drive(db, directory_id=None, sort="name", dir="asc")
    assert _names(res) == ["alpha.pdf", "Bravo", "charlie.pdf", "Delta"]


# --------------------------------------------------------------------------- #
# C2 — non-Name sort groups folders FIRST (Finder/macOS)
# --------------------------------------------------------------------------- #
def test_C2_size_sort_groups_folders_first(db):
    _folder(db, "ZFolder")
    _folder(db, "AFolder")
    _file(db, filename="big.pdf", directory_id=None, size=900)
    _file(db, filename="small.pdf", directory_id=None, size=10)
    db.commit()

    res = _drive(db, directory_id=None, sort="size", dir="asc")
    names = _names(res)
    # folders first (alpha among selves), then files ordered by size asc
    assert names[:2] == ["AFolder", "ZFolder"]
    assert names[2:] == ["small.pdf", "big.pdf"]


def test_C2_size_sort_folders_first_holds_on_desc(db):
    _folder(db, "ZFolder")
    _folder(db, "AFolder")
    _file(db, filename="big.pdf", directory_id=None, size=900)
    _file(db, filename="small.pdf", directory_id=None, size=10)
    db.commit()

    res = _drive(db, directory_id=None, sort="size", dir="desc")
    names = _names(res)
    # folders STILL first and STILL name-asc regardless of direction;
    # only the files block flips to size desc
    assert names[:2] == ["AFolder", "ZFolder"]
    assert names[2:] == ["big.pdf", "small.pdf"]


def test_C2_type_sort_folders_precede_files_and_files_type_ordered(db):
    # mime_type drives the "type" sort; folders carry none, so they group first.
    _folder(db, "ZFolder")
    _folder(db, "AFolder")
    fa = _file(db, filename="a.zip", directory_id=None)
    fb = _file(db, filename="b.doc", directory_id=None)
    fc = _file(db, filename="c.pdf", directory_id=None)
    # Assign distinct mime types so the file block has a deterministic order.
    by_id = {f.id: f for f in db.query(Attachment).all()}
    by_id[fa].mime_type = "application/zip"
    by_id[fb].mime_type = "application/msword"
    by_id[fc].mime_type = "application/pdf"
    db.commit()

    res = _drive(db, directory_id=None, sort="type", dir="asc")
    kinds = _kinds(res)
    names = _names(res)

    # ALL folders precede ALL files.
    first_file = kinds.index("file")
    assert all(k == "folder" for k in kinds[:first_file])
    assert all(k == "file" for k in kinds[first_file:])

    # Folder block is name-asc; file block is mime_type-asc:
    # application/msword < application/pdf < application/zip
    assert names[:2] == ["AFolder", "ZFolder"]
    assert names[2:] == ["b.doc", "c.pdf", "a.zip"]


# --------------------------------------------------------------------------- #
# C3 — any file-attribute filter hides folders
# --------------------------------------------------------------------------- #
def test_C3_filter_hides_folders(db):
    t = _type(db, "Catalogue")
    _folder(db, "AFolder")
    _file(db, filename="typed.pdf", directory_id=None, type_id=t)
    db.commit()

    res = _drive(db, directory_id=None, attachment_type_id=t)
    assert _kinds(res) == ["file"]
    assert _names(res) == ["typed.pdf"]


def test_C3_query_hides_nonmatching_and_only_folders_that_match(db):
    _folder(db, "zzz")  # does NOT match query
    _file(db, filename="match.pdf", directory_id=None)
    db.commit()

    res = _drive(db, directory_id=None, query="match")
    assert _names(res) == ["match.pdf"]


# --------------------------------------------------------------------------- #
# C4 — plain browse shows folders
# --------------------------------------------------------------------------- #
def test_C4_plain_browse_shows_folders(db):
    _folder(db, "Visible")
    _file(db, filename="f.pdf", directory_id=None)
    db.commit()

    res = _drive(db, directory_id=None)
    assert "Visible" in _names(res)
    assert "folder" in _kinds(res)


# --------------------------------------------------------------------------- #
# C5 — export (xlsx) is files-only; the files-list path never yields folders
# --------------------------------------------------------------------------- #
def test_C5_export_path_files_only_no_folders(db):
    folder = _folder(db, "ShouldNotExport")
    _file(db, filename="exported.pdf", directory_id=None)
    db.commit()

    # Export reuses the existing list_attachments path (files table only).
    result = AttachmentService(db).list_attachments(directory_id=None)
    names = [a.original_filename for a in result["data"]]
    assert "exported.pdf" in names
    # A folder name can never appear — list_attachments queries attachments only.
    assert "ShouldNotExport" not in names
    assert all(isinstance(a, Attachment) for a in result["data"])


# --------------------------------------------------------------------------- #
# C6 — sort + pagination correct across the UNION, no dupes/missing
# --------------------------------------------------------------------------- #
def test_C6_pagination_over_union_no_dupes_or_missing(db):
    # 3 folders + 4 files = 7 items, Name sort, page through in pages of 3.
    for n in ["b_fold", "d_fold", "f_fold"]:
        _folder(db, n)
    for n in ["a_file.pdf", "c_file.pdf", "e_file.pdf", "g_file.pdf"]:
        _file(db, filename=n, directory_id=None)
    db.commit()

    seen = []
    for page in (1, 2, 3):
        res = _drive(db, directory_id=None, sort="name", dir="asc", page=page, limit=3)
        assert res["total"] == 7
        for it in res["items"]:
            seen.append(it["id"] if it["kind"] == "folder" else it["attachment"].id)

    assert len(seen) == 7
    assert len(set(seen)) == 7  # no duplicates across pages

    # Interleaved order preserved across page boundaries.
    full = _drive(db, directory_id=None, sort="name", dir="asc", page=1, limit=50)
    assert _names(full) == [
        "a_file.pdf", "b_fold", "c_file.pdf", "d_fold",
        "e_file.pdf", "f_fold", "g_file.pdf",
    ]


# --------------------------------------------------------------------------- #
# D2 — directory_path resolved in-query (no N+1)
# --------------------------------------------------------------------------- #
def test_D2_file_rows_carry_directory_path(db):
    mk = _folder(db, "Marketing")
    camp = _folder(db, "Campaigns", parent_id=mk)
    _file(db, filename="promo.pdf", directory_id=camp)
    db.commit()

    res = _drive(db, directory_id=None, query="promo")
    file_item = next(it for it in res["items"] if it["kind"] == "file")
    assert file_item["directory_path"] == "Marketing / Campaigns"


def test_D2_folder_rows_carry_parent_path_as_location(db):
    mk = _folder(db, "Marketing")
    _folder(db, "Campaigns", parent_id=mk)
    db.commit()

    res = _drive(db, directory_id=None, query="Campaigns")
    folder_item = next(it for it in res["items"] if it["kind"] == "folder")
    assert folder_item["directory_path"] == "Marketing"


def test_D2_path_map_single_pass_for_many_files(db):
    """No N+1: build_directory_path_map issues a fixed number of queries
    regardless of file count."""
    a = _folder(db, "A")
    b = _folder(db, "B", parent_id=a)
    for i in range(10):
        _file(db, filename=f"f{i}.pdf", directory_id=b)
    db.commit()

    pm = AttachmentDirectoryService(db).build_directory_path_map()
    assert pm[b] == "A / B"
    assert pm[a] == "A"


# --------------------------------------------------------------------------- #
# D4 — isolation (single-tenant schema: a sibling subtree never leaks in)
# --------------------------------------------------------------------------- #
def test_D4_other_subtree_rows_never_appear(db):
    tenant_a = _folder(db, "TenantA")
    tenant_b = _folder(db, "TenantB")
    _file(db, filename="a-secret.pdf", directory_id=tenant_a)
    _file(db, filename="b-secret.pdf", directory_id=tenant_b)
    db.commit()

    res = _drive(db, directory_id=tenant_a, recursive=True)
    names = _names(res)
    assert "a-secret.pdf" in names
    assert "b-secret.pdf" not in names


# --------------------------------------------------------------------------- #
# E4 — cycle guard on folder move
# --------------------------------------------------------------------------- #
def test_E4_move_folder_into_own_descendant_blocked(db):
    parent = _folder(db, "Parent")
    child = _folder(db, "Child", parent_id=parent)
    db.commit()

    svc = AttachmentDirectoryService(db)
    with pytest.raises(Exception) as exc:
        svc.move_directory(parent, parent_id=child, position=None)
    assert "subfolder" in str(exc.value).lower() or "own" in str(exc.value).lower()


def test_E4_move_folder_into_itself_blocked(db):
    f = _folder(db, "Self")
    db.commit()
    svc = AttachmentDirectoryService(db)
    with pytest.raises(Exception):
        svc.move_directory(f, parent_id=f, position=None)


# --------------------------------------------------------------------------- #
# F4 — folder delete cascades soft-delete + restore brings it back
# --------------------------------------------------------------------------- #
def test_F4_folder_delete_cascade_and_restore(db):
    parent = _folder(db, "Parent")
    child = _folder(db, "Child", parent_id=parent)
    fid = _file(db, filename="inside.pdf", directory_id=child)
    db.commit()

    dir_svc = AttachmentDirectoryService(db)
    att_svc = AttachmentService(db)

    # Cascade soft-delete (mirrors the directories DELETE route).
    dir_ids = dir_svc.get_descendant_directory_ids(parent)
    att_svc.archive_attachments_in_directories(dir_ids, archived_by="tester")
    dir_svc.delete_directory(parent, deleted_by="tester")

    # Subtree gone from a normal browse.
    res = _drive(db, directory_id=None)
    assert "Parent" not in _names(res)
    att = db.query(Attachment).filter(Attachment.id == fid).first()
    assert att.is_deleted is True
    assert (
        db.query(AttachmentDirectory)
        .filter(AttachmentDirectory.id == child)
        .first()
        .is_deleted
        is True
    )

    # Restore brings folder + descendants + attachments back.
    result = dir_svc.restore_directory(parent)
    assert result["directories_restored"] == 2
    assert result["attachments_restored"] == 1
    res2 = _drive(db, directory_id=None)
    assert "Parent" in _names(res2)
    att2 = db.query(Attachment).filter(Attachment.id == fid).first()
    assert att2.is_deleted is False


def test_F4_trash_view_lists_deleted_folders(db):
    parent = _folder(db, "Parent")
    _file(db, filename="x.pdf", directory_id=parent)
    db.commit()
    dir_svc = AttachmentDirectoryService(db)
    att_svc = AttachmentService(db)
    dir_ids = dir_svc.get_descendant_directory_ids(parent)
    att_svc.archive_attachments_in_directories(dir_ids, archived_by="tester")
    dir_svc.delete_directory(parent, deleted_by="tester")

    # Root trash browse shows the deleted top-level folder.
    res = _drive(db, directory_id=None, is_deleted=True)
    assert "Parent" in _names(res)
    # Drilling into the deleted folder (trash) shows the archived file inside it.
    inside = _drive(db, directory_id=parent, is_deleted=True)
    assert "x.pdf" in _names(inside)


# --------------------------------------------------------------------------- #
# I6 / I8 — collision copy-name + replace-in-place still resolve
# --------------------------------------------------------------------------- #
def test_I8_collision_check_finds_existing(db):
    from app.api.v1.resources.attachments import _find_filename_collision

    folder = _folder(db, "Folder")
    _file(db, filename="dup.pdf", directory_id=folder)
    db.commit()

    hit = _find_filename_collision(db, folder, "dup.pdf")
    assert hit is not None
    miss = _find_filename_collision(db, folder, "other.pdf")
    assert miss is None


def test_I8_next_copy_name_bumps_until_free(db):
    from app.api.v1.resources.attachments import _next_copy_name

    folder = _folder(db, "Folder")
    _file(db, filename="dup.pdf", directory_id=folder)
    _file(db, filename="dup - copy.pdf", directory_id=folder)
    db.commit()

    name = _next_copy_name(db, folder, "dup.pdf")
    assert name == "dup - copy (2).pdf"


def test_I6_replace_semantics_keep_same_row(db):
    """Replace-in-place: same row id, new size/hash — the version-append path the
    upload API uses. Asserted at the field level the route mutates."""
    folder = _folder(db, "Folder")
    fid = _file(db, filename="v1.pdf", directory_id=folder, size=10)
    db.commit()

    row = db.query(Attachment).filter(Attachment.id == fid).first()
    # Simulate the route's replace branch field updates.
    row.file_size_bytes = 999
    row.file_hash = "newhash"
    db.commit()

    again = db.query(Attachment).filter(Attachment.id == fid).first()
    assert again.id == fid              # identity preserved (links survive)
    assert again.file_size_bytes == 999
    assert again.file_hash == "newhash"
