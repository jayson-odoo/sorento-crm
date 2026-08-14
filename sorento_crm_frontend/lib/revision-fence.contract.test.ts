/**
 * Cross-side contract: the frontend allowlist must equal the backend's fenced set.
 *
 * `FENCED_COLLECTIONS` in `lib/revision-fence.ts` is a hand-maintained mirror of
 * where the backend mounts `require_current_revision(...)`. A mirror nobody checks
 * drifts, and it drifts SILENTLY in both directions:
 *
 * * A fenced route added upstream with no entry here goes out with no
 *   `X-Revision-No`, so a stale office tab writes against a superseded revision -
 *   the exact hole UAC C-bis exists to close, reopened with no error anywhere.
 * * An entry here for a route the backend does NOT fence makes `fencedEntityId`
 *   non-null, so any 409 from that route is reported to the user as a revision
 *   conflict and blows away the query cache.
 *
 * Neither shows up in a test of either side alone, and the next person adding a
 * fenced route has no reason to know this file exists. So the check reads the Python
 * source and asserts set equality per collection. It is a text scan, not an import:
 * it matches each `@router.<verb>(...)` decorator to its closing parenthesis and
 * asks whether `require_current_revision` appears inside.
 *
 * ## Where this runs
 *
 * The `validate-frontend` job in `.github/workflows/deploy.yml` does a plain
 * `actions/checkout@v4` of the whole monorepo and then runs `npx vitest run` with
 * `working-directory: sorento_crm_frontend`, so `../sorento_crm_backend` IS on disk
 * there and this executes in CI exactly as it does locally.
 *
 * Where the backend tree genuinely is not present - a frontend-only Docker build
 * context, a sparse checkout - the assertions are skipped with the reason stated,
 * rather than failing for the wrong cause. If you are reading this because the
 * suite reported a skip, the check did NOT run and the mirror is unverified.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

import { FENCED_COLLECTIONS } from './revision-fence';

/** `{root: sub-paths}` as the frontend believes them. `''` is the record itself. */
const FRONTEND: Record<string, string[]> = Object.fromEntries(
  FENCED_COLLECTIONS.map((c) => [c.root, [...c.writes]]),
);

/**
 * Which router file backs each fenced collection root.
 *
 * The root itself is composed by `include_router` prefixes across
 * `app/api/v1/__init__.py` and the domain `__init__.py`; a rename there is a loud
 * failure (every call 404s) so it is not what this guards. What it guards is the
 * SET of fenced sub-paths within a router, which is the silent one.
 */
const ROUTERS: Record<string, string> = {
  '/api/v1/procurement/stock-inquiries': 'app/api/v1/procurement/stock_inquiries.py',
  '/api/v1/procurement/purchase-requests': 'app/api/v1/procurement/purchase_requests.py',
  '/api/v1/complaints-management/complaints': 'app/api/v1/complaints/complaints.py',
};

/** The monorepo's `sorento_crm_backend`, or null when it is not on disk. */
function findBackendRoot(): string | null {
  let dir = process.cwd();
  for (let up = 0; up < 5; up += 1) {
    const candidate = path.join(dir, 'sorento_crm_backend');
    if (fs.existsSync(path.join(candidate, 'app', 'api', 'v1'))) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

const BACKEND_ROOT = findBackendRoot();

/**
 * Sub-paths under `{root}/{id}` that one router file fences, `''` for the record.
 *
 * Walks each route decorator's argument list by counting parentheses rather than
 * regexing to the next `)`, because the `dependencies=[Depends(...)]` the fence is
 * declared in contains nested calls.
 */
function fencedSuffixes(source: string): string[] {
  const out: string[] = [];
  const decorator = /@router\.(get|post|put|patch|delete)\(/g;
  let match: RegExpExecArray | null;
  while ((match = decorator.exec(source)) !== null) {
    let depth = 1;
    let i = match.index + match[0].length;
    while (i < source.length && depth > 0) {
      if (source[i] === '(') depth += 1;
      else if (source[i] === ')') depth -= 1;
      i += 1;
    }
    const args = source.slice(match.index + match[0].length, i - 1);
    if (!args.includes('require_current_revision')) continue;
    const routePath = /^\s*"([^"]*)"/.exec(args)?.[1];
    if (routePath === undefined) continue;
    // `/{inquiry_id}/update-and-reply` -> `update-and-reply`; `/{inquiry_id}` -> ``.
    const suffix = /^\/\{[^}]+\}\/?(.*)$/.exec(routePath)?.[1];
    expect(
      suffix,
      `fenced route ${routePath} is not shaped /{id}/... - the mirror cannot express it`,
    ).toBeDefined();
    if (suffix !== undefined && !out.includes(suffix)) out.push(suffix);
  }
  return out;
}

describe.skipIf(BACKEND_ROOT === null)(
  'the frontend fence allowlist mirrors the backend',
  () => {
    for (const [root, relativePath] of Object.entries(ROUTERS)) {
      it(`matches ${relativePath} exactly`, () => {
        const file = path.join(BACKEND_ROOT as string, relativePath);
        expect(fs.existsSync(file), `${file} is missing - has the router moved?`).toBe(true);

        const backend = fencedSuffixes(fs.readFileSync(file, 'utf8'));
        const frontend = FRONTEND[root];
        expect(frontend, `no FENCED_COLLECTIONS entry for ${root}`).toBeDefined();

        const missing = backend.filter((s) => !frontend.includes(s));
        const extra = frontend.filter((s) => !backend.includes(s));

        // Named explicitly so the failure tells you what to do, not just that two
        // sorted arrays differ.
        expect(
          missing,
          `the backend fences these and the frontend sends no header for them: ` +
            `${missing.map((s) => s || '(the record itself)').join(', ')}. ` +
            `Add them to FENCED_COLLECTIONS in lib/revision-fence.ts.`,
        ).toEqual([]);
        expect(
          extra,
          `the frontend stamps X-Revision-No on these but the backend does not fence ` +
            `them: ${extra.map((s) => s || '(the record itself)').join(', ')}. ` +
            `A 409 from an unfenced route would be misreported as a revision ` +
            `conflict - remove them from FENCED_COLLECTIONS.`,
        ).toEqual([]);
      });
    }

    it('still covers 34 routes in total, as the module docstring claims', () => {
      // PUT and DELETE share the `''` suffix, so the route count is suffix count
      // plus one per collection that fences the record itself.
      let routes = 0;
      for (const [root, relativePath] of Object.entries(ROUTERS)) {
        void root;
        const source = fs.readFileSync(
          path.join(BACKEND_ROOT as string, relativePath),
          'utf8',
        );
        const decorator = /@router\.(get|post|put|patch|delete)\(/g;
        let match: RegExpExecArray | null;
        while ((match = decorator.exec(source)) !== null) {
          let depth = 1;
          let i = match.index + match[0].length;
          while (i < source.length && depth > 0) {
            if (source[i] === '(') depth += 1;
            else if (source[i] === ')') depth -= 1;
            i += 1;
          }
          if (source.slice(match.index, i).includes('require_current_revision')) routes += 1;
        }
      }
      expect(routes).toBe(34);
    });
  },
);

// A skip is not a pass. Surface it as its own assertion so a frontend-only
// environment reports "unverified" in the results rather than nothing at all.
describe.skipIf(BACKEND_ROOT !== null)('the backend source is not reachable', () => {
  it('cannot verify the fence allowlist here - the mirror is unchecked', () => {
    expect(BACKEND_ROOT).toBeNull();
  });
});
