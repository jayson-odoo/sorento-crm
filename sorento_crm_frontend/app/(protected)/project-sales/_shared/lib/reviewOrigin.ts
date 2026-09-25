/**
 * S4: Confirm returns the user to where they came from (R4). The origin travels as one query
 * param, `from`, on the review page's own URL - a full relative path (with its own query
 * string) the page pushes back to on a successful Confirm / Confirm schedule / Publish.
 * Absent (deep link, bookmark) means stay, exactly as before this slice.
 */

const ORIGIN_PARAM = 'from';

/**
 * S1 (PR #1237 review): `from` is read straight off the URL and later handed to
 * `router.push`, so a crafted `?from=https://elsewhere` would send a confirmed user
 * off-site. Only a same-app relative path is a valid origin - one leading slash, no
 * scheme, no protocol-relative `//host` (the same guard `signin/page.tsx` and
 * `products/[id]/page.tsx`'s `worklistBackHref` already use for the same reason).
 *
 * N2 (round 2 review): a leading slash alone is not enough. WHATWG URL parsing treats a
 * backslash the same as a forward slash, and strips ASCII control characters (tab,
 * newline) before resolving, so `/\evil.test`, `/\tevil.test` and `/\nevil.test` all
 * resolve to `https://evil.test/...` against the app origin even though `startsWith('/')`
 * is true. Reject any backslash or control character too.
 */
export function isSafeReviewOrigin(candidate: string | null | undefined): candidate is string {
  return (
    !!candidate &&
    candidate.startsWith('/') &&
    !candidate.startsWith('//') &&
    !/[\\\x00-\x1f]/.test(candidate)
  );
}

/** Appends the origin onto a URL an upload dialog is about to push the user to. */
export function withReviewOrigin(url: string, originHref?: string | null): string {
  if (!originHref) return url;
  const [path, search] = url.split('?');
  const params = new URLSearchParams(search);
  params.set(ORIGIN_PARAM, originHref);
  return `${path}?${params.toString()}`;
}

/** The origin for an upload launched from a project's own tab (unchanged call site, R4). */
export function projectTabOriginHref(projectId: string, tab: string): string {
  return `/project-sales/${projectId}?tab=${tab}`;
}

/**
 * The origin for an upload launched from Start (S2), which is not scoped to a row: the
 * Pipeline grid's own list state (page/sort/filters, already built for its rowHref) plus
 * `from=<pickedProjectId>` - the same param DataGridTable's own row-restore reads on mount
 * to scroll the row into view and highlight it (S4-4).
 */
export function pipelineOriginHref(pipelineListQuery: string | undefined, projectId: string): string {
  const params = new URLSearchParams(pipelineListQuery);
  params.set('from', projectId);
  return `/project-sales/pipeline?${params.toString()}`;
}
