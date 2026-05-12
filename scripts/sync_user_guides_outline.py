"""
Two-way sync between docs/user-guides/ markdown and Outline collection.

Modes:
  push   repo -> Outline (default)
  pull   Outline -> repo
  status diff repo vs Outline

Env:
  OUTLINE_BASE_URL          default https://doc.foundryx.my
  OUTLINE_API_TOKEN         required
  OUTLINE_COLLECTION_ID     default 18f78b01-bf5a-4032-934c-d5679609d553 (Sorento CRM)

State file: docs/user-guides/.outline-sync.json (path -> doc id mapping)

Mapping:
  README.md                 -> root doc "Overview"
  _shared/<file>.md         -> parent "Shared" -> child <H1 title>
  <dept>/<file>.md          -> parent "<Dept Title Cased>" -> child <H1 title>

Idempotent: re-runs upsert by saved id, fall back to title lookup, then create.

Usage:
  python scripts/sync_user_guides_outline.py push
  python scripts/sync_user_guides_outline.py pull
  python scripts/sync_user_guides_outline.py status
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDES_DIR = REPO_ROOT / "docs" / "user-guides"
STATE_FILE = GUIDES_DIR / ".outline-sync.json"

DEFAULT_BASE_URL = "https://doc.foundryx.my"
DEFAULT_COLLECTION_ID = "18f78b01-bf5a-4032-934c-d5679609d553"

PARENT_TITLES = {
    "_shared": "Shared",
    "purchasing": "1-Purchasing",
    "warehouse": "2-Warehouse",
    "marketing": "3-Marketing",
    "project-sales-admin": "4-Project Sales Admin",
    "project-sales-manager": "5-Project Sales Manager",
    "project-sales-rep": "6-Project Sales Rep",
}

ROOT_DOC_TITLE = "Overview"


def load_env() -> tuple[str, str, str]:
    load_dotenv(REPO_ROOT / "sorento_crm_backend" / ".env")
    base_url = os.environ.get("OUTLINE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    token = os.environ.get("OUTLINE_API_TOKEN")
    if not token:
        raise SystemExit("OUTLINE_API_TOKEN missing in env")
    collection_id = os.environ.get("OUTLINE_COLLECTION_ID", DEFAULT_COLLECTION_ID)
    return base_url, token, collection_id


@dataclass
class Outline:
    base_url: str
    token: str

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/{path}"
        for attempt in range(3):
            r = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"{path} -> {r.status_code} {r.text}")
            return r.json()
        raise RuntimeError(f"{path} -> rate-limited after retries")

    def list_documents(self, collection_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        offset = 0
        while True:
            data = self._post(
                "documents.list",
                {"collectionId": collection_id, "limit": 100, "offset": offset},
            )
            out.extend(data["data"])
            if len(data["data"]) < 100:
                break
            offset += 100
        return out

    def create_document(
        self,
        title: str,
        text: str,
        collection_id: str,
        parent_id: str | None = None,
        publish: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "title": title,
            "text": text,
            "collectionId": collection_id,
            "publish": publish,
        }
        if parent_id:
            payload["parentDocumentId"] = parent_id
        return self._post("documents.create", payload)["data"]

    def update_document(self, doc_id: str, title: str, text: str) -> dict[str, Any]:
        return self._post(
            "documents.update",
            {"id": doc_id, "title": title, "text": text, "append": False},
        )["data"]

    def get_document(self, doc_id: str) -> dict[str, Any]:
        return self._post("documents.info", {"id": doc_id})["data"]

    def update_collection_sharing(self, collection_id: str, sharing: bool) -> None:
        self._post(
            "collections.update",
            {"id": collection_id, "sharing": sharing},
        )


def load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def first_h1_or_filename(md_path: Path) -> str:
    text = md_path.read_text()
    m = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return md_path.stem.replace("-", " ").replace("_", " ").title()


def strip_h1(text: str) -> str:
    """Outline stores the title separately; strip the leading H1 from the body."""
    return re.sub(r"^#\s+.+?\n+", "", text, count=1, flags=re.MULTILINE)


def slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    return s


EXCLUDED_RELPATHS = {"SYNC.md"}


def discover_files() -> list[Path]:
    """Return all markdown files under GUIDES_DIR (excluding internal docs)."""
    return sorted(
        p
        for p in GUIDES_DIR.rglob("*.md")
        if str(p.relative_to(GUIDES_DIR)) not in EXCLUDED_RELPATHS
    )


def relpath(p: Path) -> str:
    return str(p.relative_to(GUIDES_DIR))


def push(args: argparse.Namespace) -> None:
    base_url, token, collection_id = load_env()
    o = Outline(base_url=base_url, token=token)

    state = load_state()
    existing = o.list_documents(collection_id)
    by_id = {d["id"]: d for d in existing}
    by_title_no_parent = {d["title"]: d for d in existing if not d.get("parentDocumentId")}

    parent_ids: dict[str, str] = {}

    def ensure_doc(
        title: str, body_md: str, parent_key: str | None, state_key: str
    ) -> str:
        cached = state.get(state_key)
        if cached and cached in by_id:
            doc = o.update_document(cached, title, body_md)
            print(f"  [update] {state_key}  -> {doc['id']}")
            return doc["id"]
        match = next(
            (
                d
                for d in existing
                if d["title"] == title
                and (
                    d.get("parentDocumentId")
                    == (parent_ids.get(parent_key) if parent_key else None)
                )
            ),
            None,
        )
        if match:
            doc = o.update_document(match["id"], title, body_md)
            print(f"  [adopt+update] {state_key}  -> {doc['id']}")
            return doc["id"]
        doc = o.create_document(
            title=title,
            text=body_md,
            collection_id=collection_id,
            parent_id=parent_ids.get(parent_key) if parent_key else None,
        )
        print(f"  [create] {state_key}  -> {doc['id']}")
        return doc["id"]

    print("[1/3] Ensure root + parent docs")
    readme = GUIDES_DIR / "README.md"
    if readme.exists():
        body = strip_h1(readme.read_text())
        state["README.md"] = ensure_doc(ROOT_DOC_TITLE, body, None, "README.md")

    for folder, title in PARENT_TITLES.items():
        folder_path = GUIDES_DIR / folder
        if not folder_path.exists():
            continue
        body = f"Department guides for **{title}**.\n"
        key = f"{folder}/__parent__"
        parent_ids[folder] = ensure_doc(title, body, None, key)
        state[key] = parent_ids[folder]

    print("[2/3] Sync child docs")
    for md in discover_files():
        rel = relpath(md)
        if rel == "README.md":
            continue
        if rel.endswith("/__parent__"):
            continue
        parts = rel.split("/")
        if len(parts) != 2:
            print(f"  [skip] unexpected layout: {rel}")
            continue
        folder, _ = parts
        if folder not in PARENT_TITLES:
            print(f"  [skip] unknown folder: {rel}")
            continue
        title = first_h1_or_filename(md)
        body = strip_h1(md.read_text())
        state[rel] = ensure_doc(title, body, folder, rel)

    print("[3/3] Save state")
    save_state(state)
    print(f"  state -> {STATE_FILE}")
    print("Done.")


def pull(args: argparse.Namespace) -> None:
    base_url, token, collection_id = load_env()
    o = Outline(base_url=base_url, token=token)

    state = load_state()
    rev = {v: k for k, v in state.items()}

    docs = o.list_documents(collection_id)
    parent_id_to_folder = {}
    for folder, _title in PARENT_TITLES.items():
        pid = state.get(f"{folder}/__parent__")
        if pid:
            parent_id_to_folder[pid] = folder

    parent_ids_set = {state.get(f"{f}/__parent__") for f in PARENT_TITLES}
    written = 0
    for d in docs:
        # Skip the parent folder docs — they don't correspond to repo files.
        if d["id"] in parent_ids_set:
            continue
        full = o.get_document(d["id"])
        body_md = full.get("text", "")
        title = full["title"]
        rel_path = rev.get(d["id"])
        if rel_path is not None and rel_path.endswith("/__parent__"):
            continue
        if rel_path is None:
            parent_id = full.get("parentDocumentId")
            if parent_id and parent_id in parent_id_to_folder:
                folder = parent_id_to_folder[parent_id]
                slug = slugify(title)
                rel_path = f"{folder}/{slug}.md"
            elif title == ROOT_DOC_TITLE:
                rel_path = "README.md"
            else:
                print(f"  [skip] unmapped doc {d['id']} '{title}'")
                continue

        out_path = GUIDES_DIR / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        full_body = f"# {title}\n\n{body_md.strip()}\n"
        if out_path.exists() and out_path.read_text() == full_body:
            continue
        out_path.write_text(full_body)
        state[rel_path] = d["id"]
        print(f"  [pull] {rel_path}  ({d['id']})")
        written += 1

    save_state(state)
    print(f"Done. {written} file(s) updated.")


def status(args: argparse.Namespace) -> None:
    base_url, token, collection_id = load_env()
    o = Outline(base_url=base_url, token=token)
    state = load_state()
    repo_paths = {relpath(p) for p in discover_files()}
    repo_paths.discard(".outline-sync.json")
    docs = o.list_documents(collection_id)
    print(f"Repo files:    {len(repo_paths)}")
    print(f"Outline docs:  {len(docs)}")
    print(f"State entries: {len(state)}")
    missing_in_state = sorted(p for p in repo_paths if p not in state)
    if missing_in_state:
        print("Missing from state (will be created on next push):")
        for p in missing_in_state:
            print(f"  - {p}")
    print("Outline doc titles:")
    for d in sorted(docs, key=lambda x: (x.get("parentDocumentId") or "", x["title"])):
        prefix = "  - " if not d.get("parentDocumentId") else "    - "
        print(f"{prefix}{d['title']}  ({d['id']})")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("push", help="repo -> Outline")
    sub.add_parser("pull", help="Outline -> repo")
    sub.add_parser("status", help="diff")
    args = parser.parse_args()
    {"push": push, "pull": pull, "status": status}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
