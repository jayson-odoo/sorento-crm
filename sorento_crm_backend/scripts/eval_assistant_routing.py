"""Assistant routing eval harness — regression baseline (PLAN-post-security-batch Item 3d).

Takes the example NL questions already authored in the module
``docs/user-guides/<module>/data-analysis.md`` guides and reports, per question,
which TOOL / CATEGORY the assistant routes to + latency. The point is a
re-runnable baseline so any future assistant change (catalog edits, intent
re-categorisation, RAG tuning) can be diffed against a committed snapshot.

Two routing modes:

* ``lexical`` (DEFAULT) — a deterministic, DB-free, LLM-free approximation of the
  assistant's RAG tool-search. It scores each question against the SAME capability
  corpus the real RAG indexes (``build_capability_documents``: tool name, category,
  intent, description, aliases, typical user questions, envelope phrases) using a
  TF-IDF overlap score, and returns the top-K tools + their categories. This is the
  source-of-truth for the committed baseline because it is fully reproducible with
  no external services and no seeded database.

  Limitation (documented per the plan): the production router ranks by pgvector
  embedding cosine (``EmbeddingReadService.search_tool_candidates``), which requires
  a seeded DB + an embeddings API call per question and therefore cannot be exercised
  offline. The lexical mode approximates routing over the identical corpus and
  categories; it is a regression *tripwire on the catalog/category mapping*, not a
  byte-for-byte replica of embedding similarity. Use ``--live`` for the real path.

* ``live`` (``--live``) — routes each question through the REAL assistant RAG path
  (``AIAssistantChatService._rag_select_tools``): embeds the query via the configured
  OpenAI key (from ``.env``) and searches the pgvector tool index. Requires a
  reachable DB with seeded tool embeddings + an embeddings key. If unavailable the
  harness reports the limitation and exits non-zero rather than pretending.

Usage (run with the backend venv from ``sorento_crm_backend/``)::

    venv/bin/python -m scripts.eval_assistant_routing                 # run, print table
    venv/bin/python -m scripts.eval_assistant_routing --update-baseline
    venv/bin/python -m scripts.eval_assistant_routing --check          # diff vs baseline, exit 1 on regression
    venv/bin/python -m scripts.eval_assistant_routing --live           # real LLM+DB routing
    venv/bin/python -m scripts.eval_assistant_routing --json out.json  # write run snapshot

``--check`` compares the routed CATEGORY (not prose, not exact tool) per question
against the committed baseline and exits non-zero if any category changed or the
question set drifted.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# scripts/ -> sorento_crm_backend/ -> sorento_crm/ (repo root)
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _SCRIPT_DIR.parent
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

GUIDES_DIR = _REPO_ROOT / "docs" / "user-guides"
BASELINE_PATH = _SCRIPT_DIR / "eval_assistant_routing.baseline.json"
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Question extraction from the data-analysis.md guides
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Question:
    module: str
    text: str


_EXAMPLE_HEADER_RE = re.compile(r"example question", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[*\-+]|\d+[.)])\s+")
_QUOTED_RE = re.compile(r'"([^"]+)"')
_HEADER_RE = re.compile(r"^\s*#{1,6}\s")
_HRULE_RE = re.compile(r"^\s*-{3,}\s*$")
# A standalone bold line like ``**Filters:**`` that starts a NON-question block.
_BOLD_BLOCK_RE = re.compile(r"^\s*\*\*[^*].*\*\*\s*$")


def _is_example_header(line: str) -> bool:
    """A header / bold-label line that opens an 'Example questions' block."""
    stripped = line.strip()
    if not _EXAMPLE_HEADER_RE.search(stripped):
        return False
    return bool(_HEADER_RE.match(line) or _BOLD_BLOCK_RE.match(line))


def parse_questions_from_file(path: Path, module: str) -> list[Question]:
    out: list[Question] = []
    seen: set[str] = set()
    in_block = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if _is_example_header(raw):
            in_block = True
            continue
        if not in_block:
            continue
        # Exit the block on the next section boundary.
        if _HEADER_RE.match(raw) or _HRULE_RE.match(raw):
            in_block = False
            continue
        if _BOLD_BLOCK_RE.match(raw) and not _LIST_ITEM_RE.match(raw):
            # Another bold label (e.g. a follow-on "**Disambiguation**") ends it.
            in_block = False
            continue
        if not _LIST_ITEM_RE.match(raw):
            # Continuation / explanation line under a numbered item — skip so we
            # only capture the question itself, not quoted snippets in the answer.
            continue
        m = _QUOTED_RE.search(raw)
        if not m:
            continue
        q = m.group(1).strip()
        if len(q) < 6:
            continue
        if q in seen:
            continue
        seen.add(q)
        out.append(Question(module=module, text=q))
    return out


def load_questions(guides_dir: Path) -> list[Question]:
    out: list[Question] = []
    for md in sorted(guides_dir.glob("*/data-analysis.md")):
        module = md.parent.name
        out.extend(parse_questions_from_file(md, module))
    return out


# ---------------------------------------------------------------------------
# Lexical router (default) — TF-IDF overlap over the capability corpus
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "by", "with",
    "is", "are", "was", "were", "be", "do", "does", "did", "how", "what", "which",
    "who", "when", "where", "this", "that", "these", "those", "their", "our", "we",
    "us", "you", "i", "it", "its", "as", "at", "from", "into", "per", "have", "has",
    "show", "list", "get", "find", "give", "me", "my", "all", "any", "can", "should",
    "would", "want", "between", "still", "right", "now", "most", "many", "much",
    "no", "not", "yes", "vs", "than", "over", "under", "each", "they", "them",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    toks = _TOKEN_RE.findall((text or "").lower())
    return [t for t in toks if len(t) >= 2 and t not in _STOPWORDS]


@dataclass
class _Doc:
    tool_name: str
    category: str
    tokens: set[str]


@dataclass
class LexicalRouter:
    docs: list[_Doc]
    idf: dict[str, float]

    @classmethod
    def build(cls) -> "LexicalRouter":
        from app.services.mcp_tool_capability_service import build_capability_documents

        cap_docs = build_capability_documents(include_planned=False)
        docs: list[_Doc] = []
        df: dict[str, int] = {}
        for cd in cap_docs:
            meta = cd.metadata or {}
            tool_name = str(meta.get("tool_name") or cd.source_key)
            category = str(meta.get("category") or "unknown")
            tokens = set(_tokenize(cd.body_text))
            docs.append(_Doc(tool_name=tool_name, category=category, tokens=tokens))
            for tok in tokens:
                df[tok] = df.get(tok, 0) + 1
        n = max(1, len(docs))
        idf = {tok: math.log((n + 1) / (count + 1)) + 1.0 for tok, count in df.items()}
        return cls(docs=docs, idf=idf)

    def route(self, query: str, top_k: int) -> list[dict[str, Any]]:
        q_tokens = set(_tokenize(query))
        scored: list[tuple[float, str, str]] = []
        for doc in self.docs:
            shared = q_tokens & doc.tokens
            if not shared:
                continue
            score = sum(self.idf.get(t, 1.0) for t in shared)
            scored.append((score, doc.tool_name, doc.category))
        # Deterministic ordering: score desc, then tool_name asc for stable ties.
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [
            {"tool": tn, "category": cat, "score": round(s, 4)}
            for (s, tn, cat) in scored[:top_k]
        ]


# ---------------------------------------------------------------------------
# Live router (--live) — real assistant RAG path
# ---------------------------------------------------------------------------

def _tool_category_map() -> dict[str, str]:
    from app.services.mcp_tool_capability_service import build_capability_documents

    out: dict[str, str] = {}
    for cd in build_capability_documents(include_planned=False):
        meta = cd.metadata or {}
        out[str(meta.get("tool_name") or cd.source_key)] = str(meta.get("category") or "unknown")
    return out


def route_live(questions: list[Question], top_k: int) -> list[dict[str, Any]]:
    """Route via the real ``_rag_select_tools`` (embeddings + pgvector)."""
    from app.database import SessionLocal
    from app.services.ai_assistant_service import AIAssistantChatService

    cat_map = _tool_category_map()
    results: list[dict[str, Any]] = []
    db = SessionLocal()
    try:
        svc = AIAssistantChatService(db)
        for q in questions:
            t0 = time.perf_counter()
            selected, _sources = svc._rag_select_tools(
                standalone_query=q.text, enabled_tools=[], top_k=top_k
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            top = [
                {
                    "tool": str(c.get("tool_name")),
                    "category": cat_map.get(str(c.get("tool_name")), "unknown"),
                    "score": c.get("score"),
                }
                for c in selected
            ]
            results.append(_result_row(q, top, latency_ms))
    finally:
        db.close()
    return results


# ---------------------------------------------------------------------------
# Run / report / compare
# ---------------------------------------------------------------------------

def _result_row(q: Question, top: list[dict[str, Any]], latency_ms: float) -> dict[str, Any]:
    routed = top[0] if top else {"tool": None, "category": "none"}
    return {
        "module": q.module,
        "question": q.text,
        "routed_tool": routed.get("tool"),
        "routed_category": routed.get("category"),
        "top_k_tools": top,
        "latency_ms": latency_ms,
    }


def run_lexical(questions: list[Question], top_k: int) -> list[dict[str, Any]]:
    router = LexicalRouter.build()
    results: list[dict[str, Any]] = []
    for q in questions:
        t0 = time.perf_counter()
        top = router.route(q.text, top_k)
        latency_ms = round((time.perf_counter() - t0) * 1000, 3)
        results.append(_result_row(q, top, latency_ms))
    return results


def build_snapshot(mode: str, top_k: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "top_k": top_k,
        "question_count": len(results),
        "results": results,
    }


def print_summary(snapshot: dict[str, Any]) -> None:
    results = snapshot["results"]
    qw = min(70, max(20, max((len(r["question"]) for r in results), default=20)))
    cw = max(len("CATEGORY"), max((len(str(r["routed_category"])) for r in results), default=8))
    header = f"{'MODULE':<16} {'QUESTION':<{qw}} {'CATEGORY':<{cw}} {'MS':>8}"
    print(header)
    print("-" * len(header))
    for r in results:
        q = r["question"]
        if len(q) > qw:
            q = q[: qw - 1] + "…"
        print(
            f"{r['module']:<16} {q:<{qw}} {str(r['routed_category']):<{cw}} "
            f"{r['latency_ms']:>8}"
        )
    print("-" * len(header))
    by_cat: dict[str, int] = {}
    for r in results:
        by_cat[str(r["routed_category"])] = by_cat.get(str(r["routed_category"]), 0) + 1
    print(f"mode={snapshot['mode']} questions={snapshot['question_count']} top_k={snapshot['top_k']}")
    print("category distribution: " + ", ".join(
        f"{c}={n}" for c, n in sorted(by_cat.items(), key=lambda x: (-x[1], x[0]))
    ))


def compare_to_baseline(current: dict[str, Any], baseline_path: Path) -> int:
    """Return 0 if no category regression vs baseline, else 1 (and print diff)."""
    if not baseline_path.exists():
        print(f"REGRESSION CHECK FAILED: no baseline at {baseline_path}", file=sys.stderr)
        print("Generate one first with --update-baseline.", file=sys.stderr)
        return 1
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    base_by_q = {r["question"]: r for r in baseline.get("results", [])}
    cur_by_q = {r["question"]: r for r in current.get("results", [])}

    regressions: list[str] = []
    added = sorted(set(cur_by_q) - set(base_by_q))
    removed = sorted(set(base_by_q) - set(cur_by_q))
    for q in added:
        regressions.append(f"  [+] NEW question not in baseline: {q!r}")
    for q in removed:
        regressions.append(f"  [-] question dropped from current run: {q!r}")
    for q, cur in cur_by_q.items():
        base = base_by_q.get(q)
        if not base:
            continue
        if cur["routed_category"] != base["routed_category"]:
            regressions.append(
                f"  [~] CATEGORY changed for {q!r}: "
                f"{base['routed_category']} -> {cur['routed_category']}"
            )

    if regressions:
        print("ROUTING REGRESSION(S) DETECTED vs committed baseline:", file=sys.stderr)
        for line in regressions:
            print(line, file=sys.stderr)
        print(
            "\nIf this change is intentional, re-snapshot with --update-baseline "
            "and commit the new baseline.",
            file=sys.stderr,
        )
        return 1
    print(f"OK: {len(cur_by_q)} questions, no category regression vs baseline.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="route via the real LLM+pgvector RAG path")
    ap.add_argument("--check", action="store_true", help="diff routed categories vs committed baseline; exit 1 on regression")
    ap.add_argument("--update-baseline", action="store_true", help="overwrite the committed baseline with this run")
    ap.add_argument("--top-k", type=int, default=3, help="tool candidates per question (default 3)")
    ap.add_argument("--guides-dir", type=Path, default=GUIDES_DIR, help="dir containing <module>/data-analysis.md")
    ap.add_argument("--baseline", type=Path, default=BASELINE_PATH, help="baseline JSON path")
    ap.add_argument("--json", type=Path, default=None, help="also write the run snapshot to this path")
    ap.add_argument("--no-table", action="store_true", help="suppress the summary table")
    args = ap.parse_args(argv)

    questions = load_questions(args.guides_dir)
    if not questions:
        print(f"No example questions found under {args.guides_dir}", file=sys.stderr)
        return 2

    mode = "live" if args.live else "lexical"
    if args.live:
        try:
            results = route_live(questions, args.top_k)
        except Exception as exc:  # noqa: BLE001 — surface the limitation clearly
            print(
                "LIVE routing unavailable (needs a reachable DB with seeded tool "
                f"embeddings + an embeddings API key): {exc}",
                file=sys.stderr,
            )
            print(
                "Fall back to the default lexical mode (no --live) for the "
                "reproducible baseline.",
                file=sys.stderr,
            )
            return 3
    else:
        results = run_lexical(questions, args.top_k)

    snapshot = build_snapshot(mode, args.top_k, results)

    if not args.no_table:
        print_summary(snapshot)

    if args.json:
        args.json.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nWrote run snapshot -> {args.json}")

    if args.update_baseline:
        if args.live:
            print("Refusing to write the baseline from --live (non-deterministic). "
                  "Generate the baseline in lexical mode.", file=sys.stderr)
            return 4
        args.baseline.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nWrote baseline -> {args.baseline}")
        return 0

    if args.check:
        return compare_to_baseline(snapshot, args.baseline)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
