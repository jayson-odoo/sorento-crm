"""
Bulk-import batch_id stamping smoke test.

Asserts that the bulk ZIP processor wires `upload_batch_id` onto every
`AttachmentCreate` it constructs, equal to the `import_jobs.job_id`. We
test by static inspection of the function source so the assertion is
robust against the heavy DB / RQ scaffolding the full task expects.

See docs/plans/PLAN-upload-activity-drawer.md §4.2 and
app/tasks/import_tasks.py.
"""
import inspect

from app.tasks import import_tasks


def test_bulk_import_attachment_create_stamps_upload_batch_id():
    src = inspect.getsource(import_tasks.process_attachment_bulk_import)
    # The new attachment branch must pass upload_batch_id=job_id_str.
    assert "upload_batch_id=job_id_str" in src, (
        "process_attachment_bulk_import is no longer stamping upload_batch_id on "
        "new AttachmentCreate rows; see PLAN-upload-activity-drawer.md §4.2."
    )


def test_bulk_import_replace_branch_stamps_upload_batch_id():
    src = inspect.getsource(import_tasks.process_attachment_bulk_import)
    assert "existing_to_replace.upload_batch_id = job_id_str" in src, (
        "Replace-in-place branch of bulk import must also stamp upload_batch_id "
        "so replaced rows still group under the same drawer session."
    )
