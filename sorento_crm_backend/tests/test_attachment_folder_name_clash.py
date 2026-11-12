"""FILES-MOVE-DUPLICATE: same-name files in a folder are allowed, and every clash is asked.

History: production returned 500 on "Move to..." because a partial unique index
(``ux_attachments_dir_lower_filename_active``, migration 198) allowed one file per
(folder, lower(original_filename)). The owner then ruled (12 Nov, 17:35): "files we should
allow same name, google drive also can". So the index is dropped (migration
``fmd_0001_drop_dir_name_unique``) and two files may share a name in one folder.

What stays: every action that would put a second file of the same VISIBLE name (any case)
into a folder asks first (owner, hand test 2: moving away and back must warn). The answers
are Keep both (same name), Rename (a free "name (1)"), Replace (the file there goes to
Trash) or Skip; Cancel stops the whole action. The hidden original name no longer counts.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.resources import Attachment, AttachmentDirectory
from app.schemas.resources import AttachmentUpdate
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.error_handler import AppException
from app.services.resources_service import AttachmentService, AttachmentDirectoryService

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


def _names_in(db, folder_id: str) -> list[str]:
    db.expire_all()
    return sorted(
        r.stored_filename
        for r in db.query(Attachment).filter(
            Attachment.directory_id == folder_id, Attachment.is_deleted.is_(False)
        )
    )


def _assert_plain(message: str, file_name: str, folder_name: str) -> None:
    assert message == f"{file_name} already exists in {folder_name}.", message
    for leak in ("duplicate key", "UniqueViolation", "ux_attachments", "psycopg2", "UPDATE "):
        assert leak not in message


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


# --- the rule change: same names are allowed --------------------------------------- #


def test_two_files_of_one_name_can_live_in_one_folder(db):
    """The unique index is gone: same original and same visible name, one folder."""
    folder = _folder(db, "Folder A")
    _file(db, "photo.jpg", folder)
    _file(db, "photo.jpg", folder)

    assert _names_in(db, folder) == ["photo.jpg", "photo.jpg"]


def test_the_model_no_longer_declares_the_unique_index():
    names = {ix.name for ix in Attachment.__table__.indexes}
    assert "ux_attachments_dir_lower_filename_active" not in names


# --- single move (PUT directory_id) ------------------------------------------------ #


def test_move_into_a_folder_holding_the_same_visible_name_asks_first(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "PHOTO.JPG", folder_b)
    moving = _file(db, "photo.jpg", folder_a)
    _file(db, "photo (1).jpg", folder_b)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert ei.value.status_code == 409
    assert ei.value.code == "ATTACHMENT_MOVE_NAME_CLASH"
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder B")
    details = ei.value.detail["details"]
    assert details["folder_name"] == "Folder B"
    assert details["existing_file_name"] == "PHOTO.JPG"
    assert details["suggested_name"] == "photo (2).jpg"
    assert "existing_attachment_id" not in details
    assert _reload(db, moving.id).directory_id == folder_a


def test_the_hidden_original_name_no_longer_counts(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b, original="photo.jpg")
    moving = _file(db, "holiday.jpg", folder_a, original="photo.jpg")

    AttachmentService(db).update_attachment(moving.id, AttachmentUpdate(directory_id=folder_b))

    assert _reload(db, moving.id).directory_id == folder_b


def test_deleted_files_and_the_root_never_clash(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    gone = _file(db, "photo.jpg", folder_b)
    gone.is_deleted = True
    _file(db, "photo.jpg", None)
    db.flush()
    one = _file(db, "photo.jpg", folder_a)
    two = _file(db, "photo.jpg", _folder(db, "Folder C"))
    service = AttachmentService(db)

    service.update_attachment(one.id, AttachmentUpdate(directory_id=folder_b))
    service.update_attachment(two.id, AttachmentUpdate(directory_id=None))

    assert _reload(db, one.id).directory_id == folder_b
    assert _reload(db, two.id).directory_id is None


def test_keep_both_moves_in_under_the_same_name(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)

    AttachmentService(db).update_attachment(
        moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="keep")
    )

    assert _names_in(db, folder_b) == ["photo.jpg", "photo.jpg"]


def test_rename_choice_changes_only_the_visible_name(db):
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
    assert (row.directory_id, row.stored_filename, row.original_filename) == (folder_b, "photo (1).jpg", "photo.jpg")
    assert row.file_path == key_before


def test_rename_choice_to_a_name_that_is_also_taken_asks_again(db):
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
    assert _reload(db, moving.id).directory_id == folder_a


def test_rename_choice_needs_a_name(db):
    folder_a = _folder(db, "Folder A")
    moving = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            moving.id, AttachmentUpdate(directory_id=_folder(db, "Folder B"), on_conflict="rename")
        )

    assert ei.value.status_code == 400


def test_replace_trashes_the_file_there_and_moves_this_one(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    # Ids pinned so the moving row sorts first: the trashed row is flushed on its own first.
    tail = uuid.uuid4().hex[:12]
    existing = _file(db, "photo.jpg", folder_b, id=f"ffffffff-ffff-4fff-8fff-{tail}")
    moving = _file(db, "photo.jpg", folder_a, id=f"00000000-0000-4000-8000-{tail}")

    AttachmentService(db).update_attachment(
        moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace"), actor_id=None
    )

    assert _reload(db, existing.id).is_deleted is True
    assert _reload(db, moving.id).directory_id == folder_b


def test_replace_refuses_another_users_private_file(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    theirs = _file(db, "photo.jpg", folder_b)
    _make_private(db, theirs, str(uuid.uuid4()))
    mine = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            mine.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace"), actor_id=str(uuid.uuid4())
        )

    assert ei.value.status_code == 409
    assert "private" in ei.value.detail["message"]
    assert _reload(db, theirs.id).is_deleted is False


def test_a_clash_never_names_another_users_private_file(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    theirs = _file(db, "PHOTO.jpg", folder_b)
    _make_private(db, theirs, str(uuid.uuid4()))
    mine = _file(db, "photo.jpg", folder_a)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(
            mine.id, AttachmentUpdate(directory_id=folder_b), actor_id=str(uuid.uuid4())
        )

    assert ei.value.detail["details"]["existing_file_name"] is None


def test_replace_guard_runs_on_the_row_it_trashes(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    existing = _file(db, "photo.jpg", folder_b)
    moving = _file(db, "photo.jpg", folder_a)
    seen: list[str] = []

    def guard(row):
        seen.append(str(row.id))
        raise AppException(status_code=403, message="no")

    with pytest.raises(AppException):
        AttachmentService(db).update_attachment(
            moving.id, AttachmentUpdate(directory_id=folder_b, on_conflict="replace"), replace_guard=guard
        )

    assert seen == [existing.id]
    assert _reload(db, existing.id).is_deleted is False


# --- rename inside a folder ---------------------------------------------------------- #


def test_rename_to_a_name_already_in_the_folder_asks_first(db):
    folder = _folder(db, "Folder B")
    _file(db, "two.jpg", folder)
    one = _file(db, "one.jpg", folder)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).update_attachment(one.id, AttachmentUpdate(stored_filename="TWO.jpg"))

    assert ei.value.status_code == 409
    _assert_plain(ei.value.detail["message"], "TWO.jpg", "Folder B")
    assert _reload(db, one.id).stored_filename == "one.jpg"


def test_rename_with_keep_both_gives_the_same_name(db):
    folder = _folder(db, "Folder B")
    _file(db, "two.jpg", folder)
    one = _file(db, "one.jpg", folder)

    AttachmentService(db).update_attachment(one.id, AttachmentUpdate(stored_filename="two.jpg", on_conflict="keep"))

    assert _names_in(db, folder) == ["two.jpg", "two.jpg"]


def test_rename_to_its_own_name_in_another_case_and_outside_folders_is_fine(db):
    folder = _folder(db, "Folder A")
    own = _file(db, "photo.jpg", folder)
    _file(db, "photo.jpg", None)
    loose = _file(db, "draft.jpg", None)
    service = AttachmentService(db)

    service.update_attachment(own.id, AttachmentUpdate(stored_filename="Photo.JPG"))
    service.update_attachment(loose.id, AttachmentUpdate(stored_filename="photo.jpg"))

    assert _reload(db, own.id).stored_filename == "Photo.JPG"
    assert _reload(db, loose.id).stored_filename == "photo.jpg"


def test_owner_case_move_away_and_back_warns(db):
    """Owner hand test 2: a file moves away, another file takes its name meanwhile, and
    the move back must warn instead of silently making a pair."""
    folder_p = _folder(db, "Counter Top")
    folder_q = _folder(db, "Other")
    away = _file(db, "SRTWB7237.jpg", folder_p)
    other = _file(db, "draft.jpg", folder_p)
    service = AttachmentService(db)
    service.update_attachment(away.id, AttachmentUpdate(directory_id=folder_q))
    service.update_attachment(other.id, AttachmentUpdate(stored_filename="SRTWB7237.jpg"))

    with pytest.raises(AppException) as ei:
        service.update_attachment(away.id, AttachmentUpdate(directory_id=folder_p))

    _assert_plain(ei.value.detail["message"], "SRTWB7237.jpg", "Counter Top")
    assert _reload(db, away.id).directory_id == folder_q


# --- bulk move: check first, decide, then one call ------------------------------------ #


def test_check_only_lists_every_conflict_and_moves_nothing(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    clashing = _file(db, "PHOTO.jpg", folder_a)
    ok = _file(db, "ok.jpg", folder_a)
    twin_1 = _file(db, "twin.jpg", folder_a)
    twin_2 = _file(db, "Twin.jpg", _folder(db, "Folder C"))

    updated, conflicts = AttachmentService(db).bulk_move_report(
        [clashing.id, ok.id, twin_1.id, twin_2.id], folder_b, check_only=True
    )

    assert updated == 0
    assert [c["attachment_id"] for c in conflicts] == [clashing.id, twin_2.id]
    assert conflicts[1]["existing_file_name"] == "twin.jpg"
    assert _reload(db, ok.id).directory_id == folder_a


def test_one_decision_keeps_a_hundred_pairs(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    ids = []
    for i in range(100):
        _file(db, f"scan {i}.pdf", folder_b)
        ids.append(_file(db, f"scan {i}.pdf", folder_a).id)

    result = AttachmentService(db).bulk_move_report(ids, folder_b, resolutions={i: {"action": "keep"} for i in ids})

    assert (result.updated, result.renamed, result.replaced, result.not_moved) == (100, 0, 0, [])
    assert len(_names_in(db, folder_b)) == 200


def test_one_decision_renames_a_hundred_conflicts(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    ids = []
    for i in range(100):
        _file(db, f"scan {i}.pdf", folder_b)
        ids.append(_file(db, f"scan {i}.pdf", folder_a).id)

    result = AttachmentService(db).bulk_move_report(ids, folder_b, resolutions={i: {"action": "rename"} for i in ids})

    assert (result.updated, result.renamed) == (100, 100)
    assert {_reload(db, i).stored_filename for i in ids} == {f"scan {n} (1).pdf" for n in range(100)}


def test_rename_all_of_same_named_movers_gets_distinct_names(db):
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    first = _file(db, "photo.jpg", _folder(db, "Folder A"))
    second = _file(db, "photo.jpg", _folder(db, "Folder C"))

    AttachmentService(db).bulk_move_report(
        [first.id, second.id], folder_b, resolutions={first.id: {"action": "rename"}, second.id: {"action": "rename"}}
    )

    assert {_reload(db, first.id).stored_filename, _reload(db, second.id).stored_filename} == {
        "photo (1).jpg", "photo (2).jpg"
    }


def test_mixed_decisions_in_one_call(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    old_a = _file(db, "a.jpg", folder_b)
    for n in ("b.jpg", "c.jpg", "d.jpg"):
        _file(db, n, folder_b)
    a, b, c, d = (_file(db, n, folder_a) for n in ("a.jpg", "b.jpg", "c.jpg", "d.jpg"))
    plain = _file(db, "plain.jpg", folder_a)

    result = AttachmentService(db).bulk_move_report(
        [a.id, b.id, c.id, d.id, plain.id], folder_b,
        resolutions={
            a.id: {"action": "replace"},
            b.id: {"action": "skip"},
            c.id: {"action": "rename", "name": "c final.jpg"},
            d.id: {"action": "keep"},
        },
    )

    assert (result.updated, result.renamed, result.replaced) == (4, 1, 1)
    assert [n["attachment_id"] for n in result.not_moved] == [b.id]
    assert _reload(db, old_a.id).is_deleted is True
    assert _reload(db, c.id).stored_filename == "c final.jpg"
    assert _names_in(db, folder_b).count("d.jpg") == 2


def test_a_clash_without_a_decision_is_skipped_and_named(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    _file(db, "photo.jpg", folder_b)
    clashing = _file(db, "photo.jpg", folder_a)
    ok = _file(db, "ok.jpg", folder_a)

    updated, not_moved = AttachmentService(db).bulk_move_report([clashing.id, ok.id], folder_b)

    assert updated == 1
    _assert_plain(not_moved[0]["message"], "photo.jpg", "Folder B")
    assert not_moved[0]["suggested_name"] == "photo (1).jpg"


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
    assert not_moved[0]["message"] == "You cannot change that file."


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


def test_a_skipped_file_stays_put_even_when_its_clash_is_gone(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    mine = _file(db, "photo.jpg", folder_a)

    updated, _ = AttachmentService(db).bulk_move_report([mine.id], folder_b, resolutions={mine.id: {"action": "skip"}})

    assert updated == 0
    assert _reload(db, mine.id).directory_id == folder_a


def test_replace_does_not_retrash_a_file_trashed_meanwhile(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    theirs = _file(db, "photo.jpg", folder_b)
    mine = _file(db, "photo.jpg", folder_a)
    service = AttachmentService(db)
    stale = service._folder_clash(folder_b, "photo.jpg", exclude_id=mine.id)
    db.execute(
        Attachment.__table__.update().where(Attachment.__table__.c.id == theirs.id).values(is_deleted=True)
    )

    assert service._lock_replaceable(stale, folder_b) is None


def test_rename_all_suggestion_stays_within_the_column_length(db):
    folder_a = _folder(db, "Folder A")
    folder_b = _folder(db, "Folder B")
    long_name = "x" * 251 + ".pdf"
    _file(db, long_name, folder_b)
    mine = _file(db, long_name, folder_a)

    AttachmentService(db).bulk_move_report([mine.id], folder_b, resolutions={mine.id: {"action": "rename"}})

    new = _reload(db, mine.id).stored_filename
    assert len(new) <= 255 and new.endswith(" (1).pdf")


# --- restore from Trash ---------------------------------------------------------------- #


def _trashed(db, name: str, folder: str) -> Attachment:
    row = _file(db, name, folder)
    AttachmentService(db).archive_attachment(row.id, None)
    return row


def test_restore_into_a_folder_holding_the_same_name_asks_first(db):
    folder = _folder(db, "Folder B")
    gone = _trashed(db, "photo.jpg", folder)
    _file(db, "photo.jpg", folder)

    with pytest.raises(AppException) as ei:
        AttachmentService(db).restore_attachment(gone.id)

    assert ei.value.code == "ATTACHMENT_MOVE_NAME_CLASH"
    _assert_plain(ei.value.detail["message"], "photo.jpg", "Folder B")
    assert ei.value.detail["details"]["suggested_name"] == "photo (1).jpg"
    assert _reload(db, gone.id).is_deleted is True


def test_restore_with_keep_rename_or_replace(db):
    folder = _folder(db, "Folder B")
    kept = _trashed(db, "a.jpg", folder)
    renamed = _trashed(db, "b.jpg", folder)
    replaced = _trashed(db, "c.jpg", folder)
    _file(db, "a.jpg", folder)
    _file(db, "b.jpg", folder)
    there = _file(db, "c.jpg", folder)
    service = AttachmentService(db)

    service.restore_attachment(kept.id, on_conflict="keep")
    service.restore_attachment(renamed.id, on_conflict="rename")
    service.restore_attachment(replaced.id, on_conflict="replace")

    assert _names_in(db, folder) == ["a.jpg", "a.jpg", "b (1).jpg", "b.jpg", "c.jpg"]
    assert _reload(db, there.id).is_deleted is True


def test_bulk_restore_checks_first_and_takes_one_decision_each(db):
    folder = _folder(db, "Folder B")
    clash = _trashed(db, "photo.jpg", folder)
    free = _trashed(db, "free.jpg", folder)
    _file(db, "photo.jpg", folder)
    service = AttachmentService(db)

    restored, conflicts = service.bulk_restore_report([clash.id, free.id], check_only=True)
    assert restored == 0
    assert [c["attachment_id"] for c in conflicts] == [clash.id]
    assert _reload(db, free.id).is_deleted is True, "a check-only call restored a file"

    result = service.bulk_restore_report([clash.id, free.id], resolutions={clash.id: {"action": "keep"}})
    assert (result.updated, result.not_moved) == (2, [])
    assert _names_in(db, folder) == ["free.jpg", "photo.jpg", "photo.jpg"]


def test_folder_restore_brings_everything_back(db):
    folder = _folder(db, "Folder A")
    for name in ("photo.jpg", "other.jpg"):
        row = _file(db, name, folder)
        row.is_deleted = True
    db.flush()
    _file(db, "photo.jpg", folder)
    directory = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == folder).one()
    directory.is_deleted = True
    db.flush()

    result = AttachmentDirectoryService(db).restore_directory(folder)

    assert result["attachments_restored"] == 2
    assert _names_in(db, folder) == ["other.jpg", "photo.jpg", "photo.jpg"]


# --- upload and other writers ----------------------------------------------------------- #


def test_upload_service_accepts_a_same_name_file(db):
    """The upload route asks (Keep both / Create copy / Replace); the service just stores."""
    folder = _folder(db, "Folder A")
    _file(db, "photo.jpg", folder)

    _file(db, "photo.jpg", folder)

    assert _names_in(db, folder) == ["photo.jpg", "photo.jpg"]


def test_zip_import_collision_is_the_visible_name(db):
    from app.api.v1.resources.attachments import _folder_name_collision

    folder = _folder(db, "Folder A")
    twin = _file(db, "invoice.pdf", folder, original="old-invoice.pdf")
    _file(db, "holiday.jpg", folder, original="photo.jpg")

    assert str(_folder_name_collision(db, folder, "INVOICE.pdf").id) == twin.id
    assert _folder_name_collision(db, folder, "photo.jpg") is None


def test_catalogue_pdf_name_skips_a_visible_twin(db):
    from app.services.catalogue_photo_service import _free_pdf_name

    folder = _folder(db, "Catalogues")
    _file(db, "catalogue.pdf", folder, original="older-upload.pdf")
    root = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == folder).one()

    assert _free_pdf_name(db, root, "catalogue.pdf") == "catalogue - copy.pdf"


def test_bulk_restore_check_only_sees_two_trashed_files_of_one_name(db):
    """Review: two files of one name coming back to one folder - the second is asked about."""
    folder = _folder(db, "Folder B")
    first = _trashed(db, "photo.jpg", folder)
    second = _trashed(db, "PHOTO.jpg", folder)

    _restored, conflicts = AttachmentService(db).bulk_restore_report([first.id, second.id], check_only=True)

    assert [c["attachment_id"] for c in conflicts] == [second.id]
