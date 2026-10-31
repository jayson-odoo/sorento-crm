"""
Two-way sync between documentation/user-guides/ markdown and Outline collection.

Modes:
  push   repo -> Outline (default)
  pull   Outline -> repo
  status diff repo vs Outline
  dry-run print the push plan (no network call)
  check  validate the repo layout + titles (no network, stdlib only; PR gate)

Env:
  OUTLINE_BASE_URL          default https://doc.foundryx.my
  OUTLINE_API_TOKEN         required
  OUTLINE_COLLECTION_ID     default 18f78b01-bf5a-4032-934c-d5679609d553 (Sorento CRM)

State file: documentation/user-guides/.outline-sync.json (path -> doc id mapping)

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
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# `requests` and `python-dotenv` are imported where they are used, so `check`
# and `dry-run` run on a bare python3 (the PR gate installs nothing for them).


REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDES_DIR = REPO_ROOT / "documentation" / "user-guides"
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
    "technical-team": "7-Technical Team",
    # Module data guides - published once the module is ready. `commercial` is
    # deliberately ABSENT (held until the module is restored/enabled per the
    # audit decision log) and is enforced by HELD_FOLDERS below.
    "inventory": "8-Inventory",
    "delivery-orders": "9-Delivery Orders",
    "product": "10-Product",
    "sla": "11-SLA",
    "supply-chain": "12-Supply Chain",
    "procurement": "13-Procurement",
    "complaints": "14-Complaints",
    "system-management": "15-System Management",
    "user-management": "16-User Management",
}

# Folders that are intentionally HELD back from Outline publishing. They MUST
# NEVER appear in PARENT_TITLES (the publish allowlist). `_assert_no_held_folders`
# RAISES if one ever does - a passive "skip unknown folder" is not enough to
# stop an accidental leak, so we fail loudly instead of relying on discipline.
HELD_FOLDERS = frozenset({"commercial"})

ROOT_DOC_TITLE = "Overview"

# Outline refuses a longer title with a 400 ("Document title must be 100
# characters or less"); run 41178406314 died part-way through a push on one.
MAX_TITLE_LEN = 100


def _assert_no_held_folders() -> None:
    """Hard safeguard: refuse to publish if a held folder leaked into the allowlist.

    Raises ``RuntimeError`` (loud, blocks push + dry-run) when any folder in
    ``HELD_FOLDERS`` is present in ``PARENT_TITLES``.
    """
    leaked = sorted(HELD_FOLDERS & set(PARENT_TITLES))
    if leaked:
        raise RuntimeError(
            "REFUSING TO PUBLISH: held folder(s) "
            f"{leaked} are present in PARENT_TITLES (the publish allowlist). "
            "These modules are held until restored/enabled per the audit "
            "decision log - remove them from PARENT_TITLES before syncing."
        )


def load_env() -> tuple[str, str, str]:
    from dotenv import load_dotenv

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
        import requests

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

    def current_user(self) -> dict[str, Any] | None:
        """The API token's own user (``auth.info``), or None when Outline will not say."""
        try:
            return self._post("auth.info", {})["data"]["user"]
        except Exception as exc:
            print(f"  [warn] auth.info failed ({exc}); the sync's own edits cannot be told apart")
            return None

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


def validate_guides() -> list[str]:
    """Every reason a push would skip or fail a page, found with NO network call.

    - a guide folder in neither PARENT_TITLES nor HELD_FOLDERS (its pages
      would be skipped as "unknown folder" and never reach Outline);
    - a markdown file outside the ``<folder>/<page>.md`` layout;
    - a page, parent or root title longer than Outline's MAX_TITLE_LEN;
    - a held folder present in PARENT_TITLES.

    Returns the problems, one line each; empty means the push can publish all.
    """
    problems: list[str] = []
    leaked = sorted(HELD_FOLDERS & set(PARENT_TITLES))
    if leaked:
        problems.append(f"held folder(s) {leaked} are in PARENT_TITLES (the publish allowlist)")

    # A folder holding no markdown (images only, say) is not a guide folder.
    folders = sorted(
        p.name for p in GUIDES_DIR.iterdir() if p.is_dir() and any(p.rglob("*.md"))
    )
    for folder in folders:
        if folder not in PARENT_TITLES and folder not in HELD_FOLDERS:
            problems.append(
                f"{folder}/: guide folder is not mapped - add it to PARENT_TITLES "
                "(or HELD_FOLDERS) in scripts/sync_user_guides_outline.py"
            )

    def check_title(where: str, title: str) -> None:
        if len(title) > MAX_TITLE_LEN:
            problems.append(
                f"{where}: title is {len(title)} characters, Outline allows "
                f"{MAX_TITLE_LEN}: \"{title}\""
            )

    check_title("README.md", ROOT_DOC_TITLE)
    for folder, title in PARENT_TITLES.items():
        check_title(f"PARENT_TITLES[{folder!r}]", title)

    for md in discover_files():
        rel = relpath(md)
        if rel == "README.md":
            continue
        parts = rel.split("/")
        if len(parts) != 2:
            problems.append(f"{rel}: unexpected layout, a guide must be <folder>/<page>.md")
            continue
        if parts[0] in HELD_FOLDERS:
            continue
        check_title(rel, first_h1_or_filename(md))
    return problems


def check(args: argparse.Namespace) -> None:
    """PR gate: fail when a push would skip or reject any guide page."""
    problems = validate_guides()
    if problems:
        print("User guides would not all publish to Outline:")
        for line in problems:
            print(f"  - {line}")
        raise SystemExit(1)
    print(f"OK: every guide under {GUIDES_DIR.relative_to(REPO_ROOT)} maps to Outline and fits its limits.")


def plan_push() -> tuple[list[str], list[str]]:
    """Compute, with NO network call, the create/update plan for a push.

    Runs the held-folder guard first, then walks the repo exactly like
    ``push()`` to report which docs WOULD be created or updated and which
    folders are skipped (not in the allowlist). ``create`` vs ``update`` is
    derived from the saved state file: a doc with a saved id updates in place;
    otherwise it is created on the next push.

    Returns ``(plan_lines, skipped)``.
    """
    _assert_no_held_folders()
    state = load_state()
    plan: list[str] = []
    skipped: list[str] = []

    def verb(key: str) -> str:
        return "update" if state.get(key) else "create"

    readme = GUIDES_DIR / "README.md"
    if readme.exists():
        plan.append(f"[{verb('README.md')}] README.md  ->  \"{ROOT_DOC_TITLE}\"")
    for folder, title in PARENT_TITLES.items():
        if not (GUIDES_DIR / folder).exists():
            continue
        key = f"{folder}/__parent__"
        plan.append(f"[{verb(key)}] {folder}/  (parent)  ->  \"{title}\"")

    for md in discover_files():
        rel = relpath(md)
        if rel == "README.md":
            continue
        parts = rel.split("/")
        if len(parts) != 2:
            skipped.append(f"{rel}  (unexpected layout)")
            continue
        folder = parts[0]
        if folder not in PARENT_TITLES:
            skipped.append(rel)
            continue
        title = first_h1_or_filename(md)
        plan.append(f"[{verb(rel)}] {rel}  ->  \"{title}\"")

    return plan, skipped


def dry_run(args: argparse.Namespace) -> None:
    """Print the exact push plan without touching Outline (no network call)."""
    plan, skipped = plan_push()
    print("DRY RUN - no Outline calls made. The following docs WOULD publish:\n")
    for line in plan:
        print(f"  {line}")
    print(f"\nTotal docs to create/update: {len(plan)}")
    if skipped:
        print("\nSKIPPED (folder not in publish allowlist - will NOT publish):")
        for s in skipped:
            print(f" - {s}")
    print(
        "\nHeld-folder check: "
        + (
            f"OK - {sorted(HELD_FOLDERS)} held back (not published)."
            if not (HELD_FOLDERS & set(PARENT_TITLES))
            else "FAILED"
        )
    )
    problems = validate_guides()
    if problems:
        print("\nValidation FAILED (push would skip or reject these):")
        for line in problems:
            print(f"  - {line}")
        raise SystemExit(1)
    print("Validation: OK")
    print("Done (dry run).")


def push(args: argparse.Namespace) -> None:
    # Hard safeguard FIRST - fail loudly before any network call if a held
    # folder (e.g. commercial) ever leaked into PARENT_TITLES.
    _assert_no_held_folders()
    base_url, token, collection_id = load_env()
    o = Outline(base_url=base_url, token=token)

    state = load_state()
    existing = o.list_documents(collection_id)
    by_id = {d["id"]: d for d in existing}
    by_title_no_parent = {d["title"]: d for d in existing if not d.get("parentDocumentId")}

    parent_ids: dict[str, str] = {}
    failures: list[str] = []

    force = os.environ.get("OUTLINE_SYNC_FORCE", "").lower() in ("1", "true", "yes")
    self_id = sync_user_id(o)
    kept: list[str] = []

    def update_if_changed(doc: dict[str, Any], title: str, body_md: str, state_key: str, verb: str) -> str:
        if doc["title"] == title and _same_text(_outline_text(o, doc), body_md):
            print(f"  [same] {state_key}")
            return doc["id"]
        page = GUIDES_DIR / state_key
        if not force and not state_key.endswith("/__parent__") and outline_is_newer(page, doc, self_id):
            # Pull has not brought this Outline edit back yet: overwriting it
            # would lose it. The next scheduled pull opens the PR for it.
            kept.append(state_key)
            print(f"  [keep] {state_key}  (Outline copy edited after the repo commit, pull it)")
            return doc["id"]
        updated = o.update_document(doc["id"], title, body_md)
        print(f"  [{verb}] {state_key}  -> {updated['id']}")
        return updated["id"]

    def ensure_doc(
        title: str, body_md: str, parent_key: str | None, state_key: str
    ) -> str:
        cached = state.get(state_key)
        if cached and cached in by_id:
            return update_if_changed(by_id[cached], title, body_md, state_key, "update")
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
            return update_if_changed(match, title, body_md, state_key, "adopt+update")
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
        try:
            state["README.md"] = ensure_doc(ROOT_DOC_TITLE, body, None, "README.md")
        except Exception as exc:  # keep going: one bad page must not stop the rest
            failures.append(f"README.md: {exc}")
            print(f"  [FAIL] README.md  {exc}")

    for folder, title in PARENT_TITLES.items():
        folder_path = GUIDES_DIR / folder
        if not folder_path.exists():
            continue
        body = f"Department guides for **{title}**.\n"
        key = f"{folder}/__parent__"
        try:
            parent_ids[folder] = ensure_doc(title, body, None, key)
        except Exception as exc:
            failures.append(f"{key}: {exc}")
            print(f"  [FAIL] {key}  {exc}")
            continue
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
        if folder not in parent_ids:
            failures.append(f"{rel}: not pushed, its parent {folder}/__parent__ failed")
            print(f"  [FAIL] {rel}  parent failed")
            continue
        title = first_h1_or_filename(md)
        body = strip_h1(md.read_text())
        try:
            state[rel] = ensure_doc(title, body, folder, rel)
        except Exception as exc:
            failures.append(f"{rel}: {exc}")
            print(f"  [FAIL] {rel}  {exc}")

    print("[3/3] Save state")
    save_state(state)
    print(f"  state -> {STATE_FILE}")
    if kept:
        print(f"\n{len(kept)} page(s) kept (Outline is newer; set OUTLINE_SYNC_FORCE=1 to overwrite):")
        for key in kept:
            print(f"  - {key}")
    if failures:
        print(f"\n{len(failures)} page(s) FAILED to push:")
        for line in failures:
            print(f"  - {line}")
        raise SystemExit(1)
    print("Done.")


def _repo_committed_at(path: Path) -> datetime | None:
    """Last commit time of `path` in git, or None when git has no history for it."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return datetime.fromisoformat(out) if out else None


def _outline_updated_at(doc: dict[str, Any]) -> datetime | None:
    raw = doc.get("updatedAt")
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def repo_is_newer(path: Path, doc: dict[str, Any]) -> bool:
    """True when the repo copy was committed after Outline's copy was last edited.

    Pull must not overwrite such a file: the repo edit has simply not been
    pushed yet, so Outline's copy is the older one. Needs full git history
    (the workflow checks out with fetch-depth 0).
    """
    if not path.exists():
        return False
    committed = _repo_committed_at(path)
    updated = _outline_updated_at(doc)
    return committed is not None and updated is not None and updated <= committed


def learn_state_by_title(state: dict[str, str], docs: list[dict[str, Any]]) -> list[str]:
    """Fill state entries the repo lacks by matching Outline titles to repo pages.

    The push saves new doc ids only in the runner; if that state never reached
    main, pull would otherwise see the pushed docs as unmapped and write them
    back under a slug filename, duplicating the page. Matches root docs to
    PARENT_TITLES (and ROOT_DOC_TITLE), then children of a known parent to the
    repo page in that folder with the same H1. Never overrides a saved id.
    Returns the keys it learnt.
    """
    learnt: list[str] = []
    known_ids = set(state.values())
    roots = {d["title"]: d["id"] for d in docs if not d.get("parentDocumentId")}
    for folder, title in PARENT_TITLES.items():
        key = f"{folder}/__parent__"
        if not state.get(key) and title in roots and roots[title] not in known_ids:
            state[key] = roots[title]
            known_ids.add(roots[title])
            learnt.append(key)
    if not state.get("README.md") and ROOT_DOC_TITLE in roots and roots[ROOT_DOC_TITLE] not in known_ids:
        state["README.md"] = roots[ROOT_DOC_TITLE]
        known_ids.add(roots[ROOT_DOC_TITLE])
        learnt.append("README.md")

    folder_by_parent = {
        state[f"{f}/__parent__"]: f for f in PARENT_TITLES if state.get(f"{f}/__parent__")
    }
    page_by_title: dict[tuple[str, str], str] = {}
    for md in discover_files():
        parts = relpath(md).split("/")
        if len(parts) == 2:
            page_by_title.setdefault((parts[0], first_h1_or_filename(md)), relpath(md))
    for d in docs:
        folder = folder_by_parent.get(d.get("parentDocumentId") or "")
        if folder is None or d["id"] in known_ids:
            continue
        rel = page_by_title.get((folder, d["title"]))
        if rel and not state.get(rel):
            state[rel] = d["id"]
            known_ids.add(d["id"])
            learnt.append(rel)
    for key in learnt:
        print(f"  [learn] {key}  -> {state[key]}  (matched by title)")
    return learnt


# A dedicated sync account is recognised by its Outline display name, so that
# swapping OUTLINE_API_TOKEN for that account's key is the only step needed.
DEDICATED_ACCOUNT_RE = re.compile(r"\b(bot|sync)\b", re.IGNORECASE)


def sync_user_id(o: "Outline") -> str | None:
    """The user id whose edits count as the sync's own, or None.

    Resolves the token's user via ``auth.info`` and logs it. Only a DEDICATED
    account (display name containing "bot" or "sync", e.g. "Sorento Sync Bot")
    gets the exemption: with a person's token, that person's own Outline edits
    would read as the sync's and push would overwrite them. For a person's
    token this warns loudly and returns None, so every Outline edit after a
    repo commit is kept (at the cost of some `[keep]` noise).
    """
    user = o.current_user()
    if not user:
        return None
    name = str(user.get("name") or "")
    if DEDICATED_ACCOUNT_RE.search(name):
        print(f"  sync user: {name!r} ({user.get('id')}), dedicated account: its edits are the sync's own")
        return user.get("id")
    print(
        f"::warning title=Outline sync runs as a person's account::OUTLINE_API_TOKEN belongs to "
        f"{name!r}, not a dedicated sync account (name with 'bot' or 'sync'). Their Outline edits "
        "are protected but cannot be told apart from the sync's own; swap the secret for a "
        "dedicated account's key (documentation/user-guides/SYNC.md)."
    )
    return None


def outline_is_newer(path: Path, doc: dict[str, Any], self_id: str | None = None) -> bool:
    """True when a person edited Outline's copy after the repo page's last commit.

    An edit by ``self_id`` (the sync's own API user, i.e. an earlier push) is
    not a person's edit: Outline re-normalises the markdown it stores, so the
    text never matches byte for byte and every page would otherwise read as
    edited.

    Push must not overwrite such a page: it holds an Outline edit the pull has
    not brought back yet. The mirror of ``repo_is_newer``; unknown timestamps
    fall back to pushing.
    """
    if not path.exists():
        return False
    editor = (doc.get("updatedBy") or {}).get("id")
    if self_id is not None and editor == self_id:
        return False
    committed = _repo_committed_at(path)
    updated = _outline_updated_at(doc)
    return committed is not None and updated is not None and updated > committed


def _same_text(a: str, b: str) -> bool:
    return a.strip() == b.strip()


def _outline_text(o: "Outline", doc: dict[str, Any]) -> str:
    text = doc.get("text")
    if text is None:
        text = o.get_document(doc["id"]).get("text", "")
    return text


def pull(args: argparse.Namespace) -> None:
    base_url, token, collection_id = load_env()
    o = Outline(base_url=base_url, token=token)

    state = load_state()

    docs = o.list_documents(collection_id)
    self_id = sync_user_id(o)
    learn_state_by_title(state, docs)
    rev = {v: k for k, v in state.items()}
    parent_id_to_folder = {}
    for folder, _title in PARENT_TITLES.items():
        pid = state.get(f"{folder}/__parent__")
        if pid:
            parent_id_to_folder[pid] = folder

    parent_ids_set = {state.get(f"{f}/__parent__") for f in PARENT_TITLES}
    written = 0
    for d in docs:
        # Skip the parent folder docs - they don't correspond to repo files.
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
        editor = (full.get("updatedBy") or {}).get("id")
        if self_id is not None and editor == self_id and out_path.exists():
            # Last written by the sync itself (a push): the repo is its source,
            # and Outline's copy differs only by its markdown normalisation or
            # by an OLDER push that ran late. Pulling it would revert a newer
            # repo edit (reviewer, DOCS-SYNC-AUTO).
            print(f"  [keep] {rel_path}  (last written by the sync's own push)")
            continue
        if repo_is_newer(out_path, full):
            print(f"  [keep] {rel_path}  (repo copy is newer than Outline's, push it)")
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
            print(f" - {p}")
    print("Outline doc titles:")
    for d in sorted(docs, key=lambda x: (x.get("parentDocumentId") or "", x["title"])):
        prefix = " - " if not d.get("parentDocumentId") else "  - "
        print(f"{prefix}{d['title']}  ({d['id']})")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("push", help="repo -> Outline")
    sub.add_parser("pull", help="Outline -> repo")
    sub.add_parser("status", help="diff")
    sub.add_parser(
        "dry-run",
        help="print exactly which docs would be created/updated on push (no network call)",
    )
    sub.add_parser(
        "check",
        help="fail when a guide folder is unmapped or a title is too long (no network)",
    )
    args = parser.parse_args()
    {"push": push, "pull": pull, "status": status, "dry-run": dry_run, "check": check}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
