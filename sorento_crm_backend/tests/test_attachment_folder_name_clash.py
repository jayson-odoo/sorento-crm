"""FILES-MOVE-DUPLICATE: a file name clash inside a folder is a plain 409, never a 500.

Production, 12 Nov: "Move to..." on Resources > Files returned 500 because the
partial unique index ``ux_attachments_dir_lower_filename_active`` on
(directory_id, lower(original_filename)), active rows only (migration 198), fired
inside the UPDATE. The index stays as it is (owner, 12 Nov); every write that can hit
it (move, bulk move, upload) checks first, still catches the IntegrityError of a race,
and answers with a plain message naming the file and the folder.

Owner standing rule: one bad line never fails a whole batch. A bulk move moves every
other file and names the one that was not moved.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.resources import Attachment, AttachmentDirectory
from app.schemas.resources import AttachmentUpdate
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.error_handler import AppException
from app.services.resources_service import AttachmentService

from .test_attachment_company_stamp_on_upload import (  # noqa: F401
    _payload,
    _scope_listeners,
    _upload,
    db,
)


def _folder(db, name: str) -> str:
    row = AttachmentDirectory(id=str(uuid.uuid4()), name=name, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row.id


def _file(
    db, name: str, folder_id: str | None, original: str | None = None, id: str | None = None
) -> Attachment:
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    return _upload(
        db,
        _payload(
            db,
            id=id or str(uuid.uuid4()),
            directory_id=folder_id,
            stored_filename=name,
            original_filename=original or name,
        ),
    )


def _reload(db, attachment_id: str) -> Attachment:
    db.expire_all()
    row = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    assert row is not None
    return row


def _assert_plain(message: str, file_name: str, folder_name: str) -> None:
    assert message == f"{file_name} already exists in {folder_name}.", message
    for leak in ("duplicate key", "UniqueViolation", "ux_attachments", "psycopg2", "UPDATE "):
        assert leak not in message


# --- single move (PUT directory_id) ------------------------------------------ #


def test_move_into_a_folder_holding_the_same_name_is_a_plain_409(db):
    """The production case: the target folder already holds a file of that name."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder B")
    assert _reload(db, moving.id).directory_id == folder_a, "the clashing file moved anyway"


def test_move_clash_is_case_insensitive(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "PHOTO.JPG", folder_b)
    moving = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder B")


def test_move_ignores_a_deleted_file_of_the_same_name(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    gone = _file(db, "photo.jpg", folder_b)
    gone.is_deleted = True
    db.flush()
    moving = _file(db, "photo.jpg", folder_a)

    AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert _reload(db, moving.id).directory_id == folder_b


def test_move_clash_on_the_hidden_original_name_says_which_file_blocks_it(db):
    """The owner's stuck case: the moving file was renamed, but both files still share
    the original name the index judges. The message names both visible names."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b, original="photo.jpg")
    moving = _file(db, "holiday.jpg", folder_a, original="photo.jpg")

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert ei.value.status_code == 409
    assert ei.value.detail["message"] == (
        "holiday.jpg cannot be moved into Folder B: photo.jpg there has the same original file name."
    )
    assert _reload(db, moving.id).directory_id == folder_a


def test_move_of_a_same_visible_name_but_different_original_is_a_clash(db):
    """Owner hand test 2 (12 Nov): a folder never ends with two files of one VISIBLE name,
    whatever their hidden original names (was: allowed, because only the original counted)."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b, original="photo.jpg")
    moving = _file(db, "photo.jpg", folder_a, original="photo-2.jpg")

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder B")
    assert _reload(db, moving.id).directory_id == folder_a


def test_move_to_the_root_never_clashes(db):
    folder_a = _folder(db, "Folder A")
    _file(db, "photo.jpg", None)
    moving = _file(db, "photo.jpg", folder_a)

    AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=None))

    assert _reload(db, moving.id).directory_id is None


def test_a_race_past_the_check_is_still_a_plain_409(db, monkeypatch):
    """Two parallel moves can both pass the check; the loser hits the index. It must
    still read as the plain message, not a 500 with database text."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)
    service = AttachmentService(db)
    monkeypatch.setattr(service, "_folder_clash", lambda *a, **k: None)

    with pytest.raises(AppException) as ei:
        service.update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder B")
    assert _reload(db, moving.id).directory_id == folder_a


# --- rename never touches the index ---------------------------------------- #


def test_rename_inside_a_folder_is_unchanged_and_never_500s(db):
    """Rename edits the visible name only (the index judges the original name), so it
    cannot clash with the index; it keeps working as before."""
    folder = _folder(db, "Folder A")
    _file(db, "invoice.pdf", folder)
    other = _file(db, "draft.pdf", folder)

    AttachmentService(db).update_attachment(other.id, AttachmentUpdate(stored_filename="final.pdf"))

    assert _reload(db, other.id).stored_filename == "final.pdf"


# --- bulk move ---------------------------------------------------------------- #


def test_bulk_move_moves_the_others_and_names_the_clash(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    clashing = _file(db, "photo.jpg", folder_a)
    one = _file(db, "one.jpg", folder_a)
    two = _file(db, "two.jpg", folder_a)

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [one.id, clashing.id, two.id], folder_b
    )

    assert updated == 2
    assert [n["attachment_id"] for n in not_moved] == [clashing.id]
    assert not_moved[0]["file_name"] == "photo.jpg"
    _assert_plain(not_moved[0]["message"], "photo.jpg", "Folder B")
    assert _reload(db, one.id).directory_id == folder_b
    assert _reload(db, two.id).directory_id == folder_b
    assert _reload(db, clashing.id).directory_id == folder_a


def test_bulk_move_of_two_files_sharing_a_name_moves_the_first_only(db):
    """Two movers that clash with EACH OTHER: the first goes, the second is named."""
    folder_a = _folder(db, "Folder A")
    folder_c = _folder(db, "Folder C")
    folder_b = _folder(db, "Folder B")
    first = _file(db, "photo.jpg", folder_a)
    second = _file(db, "Photo.jpg", folder_c)

    updated, not_moved = AttachmentService(db).bulk_move_report([first.id, second.id], folder_b)

    assert updated == 1
    assert [n["attachment_id"] for n in not_moved] == [second.id]
    _assert_plain(not_moved[0]["message"], "Photo.jpg", "Folder B")
    assert _reload(db, first.id).directory_id == folder_b
    assert _reload(db, second.id).directory_id == folder_c


def test_bulk_move_count_wrapper_still_returns_the_moved_count(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    clashing = _file(db, "photo.jpg", folder_a)
    ok = _file(db, "ok.jpg", folder_a)

    assert AttachmentService(db).bulk_move([ok.id, clashing.id], folder_b) == 1


# --- upload into a folder ----------------------------------------------------- #


def test_upload_into_a_folder_holding_the_same_original_name_is_a_plain_409(db):
    """The upload route's own guard judges the visible name (and only on the same
    record); a renamed file still holding the original name slipped past it and hit
    the index as a 500."""
    folder = _folder(db, "Folder A")
    _file(db, "renamed.jpg", folder, original="photo.jpg")

    with pytest.raises(AppException) as ei:
        _file(db, "photo.jpg", folder, original="photo.jpg")

    assert ei.value.status_code == 409
    assert ei.value.detail["message"] == (
        "photo.jpg cannot be added to Folder A: renamed.jpg there has the same original file name."
    )


def test_upload_same_visible_name_on_the_index_is_a_plain_409(db):
    folder = _folder(db, "Folder A")
    _file(db, "photo.jpg", folder)

    with pytest.raises(AppException) as ei:
        _file(db, "photo.jpg", folder)

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder A")


def test_upload_of_a_new_original_name_succeeds(db):
    folder = _folder(db, "Folder A")
    _file(db, "photo.jpg", folder)

    row = _file(db, "photo - copy.jpg", folder)

    assert row.directory_id == folder


# --- the clash dialog: Replace / Rename / Skip -------------------------------- #


def test_move_clash_409_carries_what_the_dialog_needs(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    _file(db, "photo (1).jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert ei.value.code == "ATTACHMENT_MOVE_NAME_CLASH"
    details = ei.value.detail["details"]
    assert details["file_name"] == "photo.jpg"
    assert details["folder_name"] == "Folder B"
    assert "existing_attachment_id" not in details, "the 409 must not hand out another file's id"
    assert details["existing_file_name"] == "photo.jpg"
    assert details["suggested_name"] == "photo (2).jpg"


def test_replace_sends_the_file_in_the_folder_to_trash_and_moves_this_one(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    # Ids pinned so the moving row sorts FIRST: one flush writes UPDATEs in primary-key order,
    # so without the separate flush of the trashed row this always trips the index.
    tail = uuid.uuid4().hex[:12]
    existing = _file(db, "photo.jpg", folder_b, id=f"ffffffff-ffff-4fff-8fff-{tail}")
    moving = _file(db, "photo.jpg", folder_a, id=f"00000000-0000-4000-8000-{tail}")
    key_before = moving.file_path

    AttachmentService(db).update_attachment(
        moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace"), actor_id=None
    )

    replaced = _reload(db, existing.id)
    assert replaced.is_deleted is True, "the replaced file must go to Trash, not vanish"
    assert replaced.directory_id == folder_b, "Restore must bring it back to the same folder"
    moved = _reload(db, moving.id)
    assert moved.directory_id == folder_b
    assert moved.file_path == key_before


def test_replace_without_a_clash_just_moves(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    other = _file(db, "other.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)

    AttachmentService(db).update_attachment(
        moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace")
    )

    assert _reload(db, moving.id).directory_id == folder_b
    assert _reload(db, other.id).is_deleted is False


def test_rename_choice_sets_visible_and_original_name_and_keeps_the_cloudflare_key(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)
    key_before = moving.file_path

    AttachmentService(db).update_attachment(
        moving.id,
        AttachmentUpdate(directory_id=folder_b, on_conflict="rename", stored_filename="photo (1).jpg"),
    )

    row = _reload(db, moving.id)
    assert row.directory_id == folder_b
    assert row.stored_filename == "photo (1).jpg"
    # Kept as typed, brackets and all (crew pass 12 Nov: "invoice 1.pdf" lost its brackets).
    assert row.original_filename == "photo (1).jpg"
    assert row.file_path == key_before, "a rename in the clash dialog must not touch the stored object"


def test_rename_choice_to_a_name_that_also_clashes_is_another_plain_409(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    _file(db, "taken.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            moving.id,
            AttachmentUpdate(directory_id=folder_b, on_conflict="rename", stored_filename="Taken.jpg"),
        )

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "Taken.jpg", "Folder B")
    row = _reload(db, moving.id)
    assert (row.directory_id, row.stored_filename, row.original_filename) == (folder_a, "photo.jpg", "photo.jpg")


def test_rename_choice_needs_a_name(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    moving = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="rename")
        )

    assert ei.value.status_code == 400


def test_general_rename_still_changes_only_the_visible_name(db):
    folder = _folder(db, "Folder A")
    row = _file(db, "photo.jpg", folder)

    AttachmentService(db).update_attachment(row.id, AttachmentUpdate(stored_filename="holiday.jpg"))

    row = _reload(db, row.id)
    assert (row.stored_filename, row.original_filename) == ("holiday.jpg", "photo.jpg")


def test_bulk_move_not_moved_entry_carries_the_dialog_details(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    clashing = _file(db, "photo.jpg", folder_a)

    _updated, not_moved = AttachmentService(db).bulk_move_report([clashing.id], folder_b)

    entry = not_moved[0]
    assert "existing_attachment_id" not in entry
    assert entry["existing_file_name"] == "photo.jpg"
    assert entry["folder_name"] == "Folder B"
    assert entry["suggested_name"] == "photo (1).jpg"


# --- security review: Replace and the 409 respect private files ------------- #


def _make_private(db, row: Attachment, owner_id: str) -> None:
    from app.models.resources import AttachmentType
    from app.services.entity_attachment_service import PRIVATE_ATTACHMENT_TYPE_CODE

    kind = db.query(AttachmentType).filter(AttachmentType.code == PRIVATE_ATTACHMENT_TYPE_CODE).first()
    if kind is None:
        kind = AttachmentType(
            id=str(uuid.uuid4()), code=PRIVATE_ATTACHMENT_TYPE_CODE,
            type_name=f"Private {uuid.uuid4().hex[:6]}", allowed_extensions="jpg", max_file_size_mb=10,
        )
        db.add(kind)
        db.flush()
    row.attachment_type_id = kind.id
    row.uploaded_by = owner_id
    db.flush()
    db.expire_all()


def test_replace_refuses_another_users_private_file(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    theirs = _file(db, "photo.jpg", folder_b)
    _make_private(db, theirs, str(uuid.uuid4()))
    moving = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace"),
            actor_id=str(uuid.uuid4()),
        )

    assert ei.value.status_code == 409
    assert "private" in ei.value.detail["message"]
    assert _reload(db, theirs.id).is_deleted is False
    assert _reload(db, moving.id).directory_id == folder_a


def test_clash_never_names_another_users_private_file(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    theirs = _file(db, "secret-plan.jpg", folder_b, original="photo.jpg")
    _make_private(db, theirs, str(uuid.uuid4()))
    moving = _file(db, "holiday.jpg", folder_a, original="photo.jpg")

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            moving.id, AttachmentUpdate(directory_id=folder_b), actor_id=str(uuid.uuid4())
        )

    assert "secret-plan" not in ei.value.detail["message"]
    assert ei.value.detail["details"]["existing_file_name"] is None
    _assert_plain(ei.value.detail["message"], "holiday.jpg", "Folder B")
    _updated, not_moved = AttachmentService(db).bulk_move_report(
        [moving.id], folder_b, viewer_id=str(uuid.uuid4())
    )
    assert not_moved[0]["existing_file_name"] is None
    assert "secret-plan" not in not_moved[0]["message"]


def test_replace_guard_runs_on_the_row_it_trashes(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    existing = _file(db, "photo.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)
    seen: list[str] = []

    def guard(row):
        seen.append(str(row.id))
        raise AppException(status_code=403, message="no")

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace"), replace_guard=guard
        )

    assert ei.value.status_code == 403
    assert seen == [existing.id]
    assert _reload(db, existing.id).is_deleted is False


# --- review B1: restore from Trash meets the same rule ------------------------ #


def test_restoring_a_replaced_file_is_a_plain_409_not_a_500(db):
    """Replace's documented undo: the replaced file comes back from Trash, but the moved file
    now holds that name in the folder."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    existing = _file(db, "photo.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)
    service = AttachmentService(db)
    service.update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace"))

    with pytest.raises(AppException) as ei:
        service.restore_attachment(existing.id)

    assert ei.value.status_code == 409
    assert ei.value.detail["message"] == (
        "photo.jpg cannot be restored to Folder B: a file with the same name is there now. "
        "Rename or move that file first."
    )
    assert _reload(db, existing.id).is_deleted is True


def test_restoring_without_a_clash_still_works(db):
    folder = _folder(db, "Folder A")
    row = _file(db, "photo.jpg", folder)
    service = AttachmentService(db)
    service.archive_attachment(row.id, None)

    service.restore_attachment(row.id)

    assert _reload(db, row.id).is_deleted is False


def test_folder_restore_brings_back_the_others_and_names_the_clash(db):
    """One bad file never fails the batch: the folder and its other files come back."""
    from app.services.resources_service import AttachmentDirectoryService

    folder = _folder(db, "Folder A")
    clashing = _file(db, "photo.jpg", folder)
    other = _file(db, "other.jpg", folder)
    for row in (clashing, other):
        row.is_deleted = True
    db.flush()
    _file(db, "photo.jpg", folder)  # took the name while the first one sat in Trash
    directory = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == folder).one()
    directory.is_deleted = True
    db.flush()

    result = AttachmentDirectoryService(db).restore_directory(folder)

    assert result["attachments_restored"] == 1
    assert result["attachments_not_restored"] == [
        "photo.jpg cannot be restored to Folder A: a file with the same name is there now. "
        "Rename or move that file first."
    ]
    assert _reload(db, other.id).is_deleted is False
    assert _reload(db, clashing.id).is_deleted is True


def test_bulk_move_race_past_the_check_skips_only_that_file(db, monkeypatch):
    """Review S2: the per-row savepoint on its own (pre-check disabled)."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    clashing = _file(db, "photo.jpg", folder_a)
    ok = _file(db, "ok.jpg", folder_a)
    service = AttachmentService(db)
    monkeypatch.setattr(service, "_folder_clash", lambda *a, **k: None)

    updated, not_moved = service.bulk_move_report([clashing.id, ok.id], folder_b)

    assert updated == 1
    assert [n["attachment_id"] for n in not_moved] == [clashing.id]
    _assert_plain(not_moved[0]["message"], "photo.jpg", "Folder B")
    assert _reload(db, ok.id).directory_id == folder_b
    assert _reload(db, clashing.id).directory_id == folder_a


# --- hand test 12 Nov: find every conflict first, decide once, cancel moves nothing ---- #


def test_check_only_lists_every_conflict_and_moves_nothing(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    clashing = _file(db, "photo.jpg", folder_a)
    ok = _file(db, "ok.jpg", folder_a)
    twin_1 = _file(db, "twin.jpg", folder_a)
    folder_c = _folder(db, "Folder C")
    twin_2 = _file(db, "Twin.jpg", folder_c)  # clashes with another file of the same batch

    updated, conflicts = AttachmentService(db).bulk_move_report(
        [clashing.id, ok.id, twin_1.id, twin_2.id], folder_b, check_only=True
    )

    assert updated == 0
    assert [c["attachment_id"] for c in conflicts] == [clashing.id, twin_2.id]
    assert conflicts[1]["existing_file_name"] == "twin.jpg"
    for row, folder in ((clashing, folder_a), (ok, folder_a), (twin_1, folder_a), (twin_2, folder_c)):
        assert _reload(db, row.id).directory_id == folder, "a check-only call moved a file"


def test_one_decision_renames_a_hundred_conflicts_in_one_call(db):
    """100 files, 100 conflicts: one apply-to-all Rename keeps both for every file."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    ids = []
    for i in range(100):
        _file(db, f"scan {i}.pdf", folder_b)
        ids.append(_file(db, f"scan {i}.pdf", folder_a).id)

    updated, not_moved = AttachmentService(db).bulk_move_report(
        ids, folder_b, resolutions={aid: {"action": "rename"} for aid in ids}
    )

    assert (updated, not_moved) == (100, [])
    names = {_reload(db, aid).stored_filename for aid in ids}
    assert names == {f"scan {i} (1).pdf" for i in range(100)}
    assert all(_reload(db, aid).directory_id == folder_b for aid in ids)


def test_apply_to_all_rename_of_same_named_movers_gets_distinct_names(db):
    folder_a = _folder(db, "Folder A")
    folder_c = _folder(db, "Folder C")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    first = _file(db, "photo.jpg", folder_a)
    second = _file(db, "photo.jpg", folder_c)

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [first.id, second.id], folder_b,
        resolutions={first.id: {"action": "rename"}, second.id: {"action": "rename"}},
    )

    assert (updated, not_moved) == (2, [])
    assert {_reload(db, first.id).stored_filename, _reload(db, second.id).stored_filename} == {
        "photo (1).jpg", "photo (2).jpg"
    }


def test_resolutions_replace_skip_and_custom_rename_in_one_call(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    old_a = _file(db, "a.jpg", folder_b)
    _file(db, "b.jpg", folder_b)
    _file(db, "c.jpg", folder_b)
    a = _file(db, "a.jpg", folder_a)
    b = _file(db, "b.jpg", folder_a)
    c = _file(db, "c.jpg", folder_a)
    plain = _file(db, "plain.jpg", folder_a)

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [a.id, b.id, c.id, plain.id], folder_b,
        resolutions={
            a.id: {"action": "replace"},
            b.id: {"action": "skip"},
            c.id: {"action": "rename", "name": "c final.jpg"},
        },
    )

    assert updated == 3
    assert [n["attachment_id"] for n in not_moved] == [b.id]
    assert _reload(db, old_a.id).is_deleted is True
    assert _reload(db, a.id).directory_id == folder_b
    assert _reload(db, b.id).directory_id == folder_a
    assert _reload(db, c.id).stored_filename == "c final.jpg"
    assert _reload(db, plain.id).directory_id == folder_b


def test_a_refused_replace_skips_only_that_file(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "a.jpg", folder_b)
    a = _file(db, "a.jpg", folder_a)
    plain = _file(db, "plain.jpg", folder_a)

    def guard(row):
        raise AppException(status_code=403, message="You cannot change that file.")

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [a.id, plain.id], folder_b, resolutions={a.id: {"action": "replace"}}, replace_guard=guard
    )

    assert updated == 1
    assert not_moved[0]["attachment_id"] == a.id
    assert not_moved[0]["message"] == "You cannot change that file."
    assert _reload(db, plain.id).directory_id == folder_b


def test_a_custom_rename_that_is_also_taken_is_named_not_moved(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "a.jpg", folder_b)
    _file(db, "taken.jpg", folder_b)
    a = _file(db, "a.jpg", folder_a)

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [a.id], folder_b, resolutions={a.id: {"action": "rename", "name": "Taken.jpg"}}
    )

    assert updated == 0
    _assert_plain(not_moved[0]["message"], "Taken.jpg", "Folder B")
    assert _reload(db, a.id).directory_id == folder_a


def test_bulk_replace_refuses_another_users_private_file(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    theirs = _file(db, "photo.jpg", folder_b)
    _make_private(db, theirs, str(uuid.uuid4()))
    mine = _file(db, "photo.jpg", folder_a)

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [mine.id], folder_b, resolutions={mine.id: {"action": "replace"}}, actor_id=str(uuid.uuid4())
    )

    assert updated == 0
    assert "private" in not_moved[0]["message"]
    assert _reload(db, theirs.id).is_deleted is False


def test_rename_all_suggestion_stays_within_the_column_length(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    long_name = "x" * 251 + ".pdf"  # 255 characters
    _file(db, long_name, folder_b)
    mine = _file(db, long_name, folder_a)

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [mine.id], folder_b, resolutions={mine.id: {"action": "rename"}}
    )

    assert (updated, not_moved) == (1, [])
    new = _reload(db, mine.id).stored_filename
    assert len(new) <= 255 and new.endswith(" (1).pdf")


def test_a_skipped_file_stays_put_even_when_its_clash_is_gone(db):
    """Review: the user chose Skip; a race that removed the other file must not move it."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    mine = _file(db, "photo.jpg", folder_a)  # no clash left at execution

    updated, not_moved = AttachmentService(db).bulk_move_report(
        [mine.id], folder_b, resolutions={mine.id: {"action": "skip"}}
    )

    assert updated == 0
    assert [n["attachment_id"] for n in not_moved] == [mine.id]
    assert _reload(db, mine.id).directory_id == folder_a


def test_the_server_counts_what_it_renamed_and_replaced(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "a.jpg", folder_b)
    _file(db, "b.jpg", folder_b)
    a = _file(db, "a.jpg", folder_a)
    b = _file(db, "b.jpg", folder_a)
    plain = _file(db, "plain.jpg", folder_a)
    gone = _file(db, "gone.jpg", folder_a)  # chose Rename, but its clash is gone: a plain move

    result = AttachmentService(db).bulk_move_report(
        [a.id, b.id, plain.id, gone.id], folder_b,
        resolutions={a.id: {"action": "rename"}, b.id: {"action": "replace"}, gone.id: {"action": "rename"}},
    )

    assert (result.updated, result.renamed, result.replaced) == (4, 1, 1)
    assert _reload(db, gone.id).stored_filename == "gone.jpg"


def test_replace_does_not_retrash_a_file_trashed_meanwhile(db):
    """Review: re-check the locked row; a file already in Trash keeps who trashed it."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    theirs = _file(db, "photo.jpg", folder_b)
    mine = _file(db, "photo.jpg", folder_a)
    service = AttachmentService(db)
    stale = service._folder_clash(folder_b, "photo.jpg", exclude_id=mine.id)
    db.execute(
        Attachment.__table__.update()
        .where(Attachment.__table__.c.id == theirs.id)
        .values(is_deleted=True, deleted_by=None)
    )

    assert service._lock_replaceable(stale, folder_b) is None


# --- hand test 2 F2: the visible name counts on every path into a folder ------------- #


def test_owner_repro_rename_then_move_away_and_back_never_leaves_two_of_one_name(db):
    """Rename in the same folder to a name already there is refused; and a twin pair that
    already exists cannot be re-created by moving one away and back."""
    folder_p = _folder(db, "Counter Top")
    folder_q = _folder(db, "Other")
    _file(db, "SRTWB7237.jpg", folder_p)
    other = _file(db, "draft.jpg", folder_p)
    service = AttachmentService(db)

    with pytest.raises(AppException) as ei:
        service.update_attachment(other.id, AttachmentUpdate(stored_filename="SRTWB7237.JPG"))
    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "SRTWB7237.JPG", "Counter Top")
    assert _reload(db, other.id).stored_filename == "draft.jpg"

    # A pair that already exists in the data (made before this fix):
    twin = _file(db, "SRTWB7237.jpg", folder_q, original="older-upload.jpg")
    with pytest.raises(AppException):
        service.update_attachment(twin.id, AttachmentUpdate(directory_id=folder_p))
    assert _reload(db, twin.id).directory_id == folder_q


def test_rename_to_its_own_name_in_another_case_is_fine(db):
    folder = _folder(db, "Folder A")
    row = _file(db, "photo.jpg", folder)

    AttachmentService(db).update_attachment(row.id, AttachmentUpdate(stored_filename="Photo.JPG"))

    assert _reload(db, row.id).stored_filename == "Photo.JPG"


def test_rename_outside_any_folder_is_unchanged(db):
    _file(db, "photo.jpg", None)
    row = _file(db, "draft.jpg", None)

    AttachmentService(db).update_attachment(row.id, AttachmentUpdate(stored_filename="photo.jpg"))

    assert _reload(db, row.id).stored_filename == "photo.jpg"


def test_check_only_and_bulk_move_see_visible_twins(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b, original="photo.jpg")
    twin = _file(db, "photo.jpg", folder_a, original="renamed-from.jpg")
    batch_1 = _file(db, "same.jpg", folder_a, original="x1.jpg")
    batch_2 = _file(db, "same.jpg", _folder(db, "Folder C"), original="x2.jpg")
    service = AttachmentService(db)

    _u, conflicts = service.bulk_move_report([twin.id, batch_1.id, batch_2.id], folder_b, check_only=True)
    assert [c["attachment_id"] for c in conflicts] == [twin.id, batch_2.id]

    updated, not_moved = service.bulk_move_report([twin.id, batch_1.id, batch_2.id], folder_b)
    assert updated == 1
    assert {n["attachment_id"] for n in not_moved} == {twin.id, batch_2.id}


def test_keep_both_on_a_visible_twin_picks_a_name_free_on_both(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b, original="photo.jpg")
    _file(db, "photo (1).jpg", folder_b, original="something-else.jpg")
    twin = _file(db, "photo.jpg", folder_a, original="renamed-from.jpg")

    result = AttachmentService(db).bulk_move_report(
        [twin.id], folder_b, resolutions={twin.id: {"action": "rename"}}
    )

    assert (result.updated, result.renamed) == (1, 1)
    assert _reload(db, twin.id).stored_filename == "photo (2).jpg"


def test_restore_refuses_a_visible_twin(db):
    folder = _folder(db, "Folder A")
    gone = _file(db, "photo.jpg", folder, original="first.jpg")
    service = AttachmentService(db)
    service.archive_attachment(gone.id, None)
    _file(db, "photo.jpg", folder, original="second.jpg")

    with pytest.raises(AppException) as ei:
        service.restore_attachment(gone.id)

    assert ei.value.status_code == 409
    assert _reload(db, gone.id).is_deleted is True


def test_upload_refuses_a_visible_twin_with_another_original(db):
    folder = _folder(db, "Folder A")
    _file(db, "photo.jpg", folder, original="renamed-from.jpg")

    with pytest.raises(AppException) as ei:
        _file(db, "photo.jpg", folder, original="photo.jpg")

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder A")
