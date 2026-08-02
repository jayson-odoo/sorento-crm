"""Object storage that stays in this process.

Every suite that exercises a flyer UPLOAD needs this, not only the ones that
assert on the stored bytes. ``flyer_reading_service`` stores each page's banner
as it reads the file, so a test that posts a flyer and never patches storage
performs a real PUT against whatever ``STORAGE_DEFAULT_PROVIDER`` points at --
which on a developer machine is the LIVE Cloudflare R2 bucket, with the live
credentials in ``.env``.

That is not a hypothetical. 1,232 objects under ``dealer_kit_asset/`` were found
in the production bucket, written by test runs: two banners plus two thumbnails
for every upload in every run of two suites. Nothing deletes them, because the
database rows that would point at them are rolled back with the test.

It is also why those suites were slow and erratic. Four round trips to
Cloudflare per uploading test, on a laptop's network, is most of a suite's
runtime and all of its variance.

So: a fake, shared, and applied in the fixture of every suite that uploads.
"""
from __future__ import annotations


class FakeStorage:
    """Keeps every object it is handed, so a test can read the stored bytes back."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str | None]] = {}
        self.signing_fails = False

    def upload_file(self, *, file_content: bytes, file_path: str, content_type=None):
        self.objects[file_path] = (file_content, content_type)
        return file_path, f"https://cdn.test/{file_path}"

    def get_signed_url(self, key: str, expires_in: int = 3600) -> str:
        if self.signing_fails:
            raise RuntimeError("no signing key on this environment")
        return f"https://cdn.test/{key}?sig=zzt"


def patch_storage(monkeypatch) -> FakeStorage:
    """Route every upload and URL in the asset path to an in-process fake.

    Patched in BOTH namespaces. ``asset_service`` imports these by name at module
    load, so patching only ``storage_router`` leaves it holding the real ones and
    the upload reaches for a live CDN. ``resolve_signed_url`` is deliberately NOT
    patched: strict signing is under test in the asset suites, and it dispatches
    through the patched ``get_backend`` anyway.
    """
    import app.services.dealer_kit.asset_service as asset_service
    import app.services.storage_router as storage_router

    storage = FakeStorage()
    for module in (storage_router, asset_service):
        monkeypatch.setattr(module, "default_provider", lambda: "s3")
        monkeypatch.setattr(module, "get_backend", lambda provider: storage)
        monkeypatch.setattr(
            module, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}"
        )
    return storage


__all__ = ["FakeStorage", "patch_storage"]
