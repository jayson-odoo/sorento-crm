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


def test_move_of_a_same_visible_name_but_different_original_succeeds(db):
    """The index judges the original name only; a visible-name twin is not a clash."""
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b, original="photo.jpg")
    moving = _file(db, "photo.jpg", folder_a, original="photo-2.jpg")

    AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert _reload(db, moving.id).directory_id == folder_b


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
    assert row.original_filename == "photo 1.jpg" or row.original_filename == "photo (1).jpg"
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
