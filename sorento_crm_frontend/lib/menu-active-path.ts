/**
 * Which sidebar entry is the current page.
 *
 * The old rule was `path === pathname || pathname.startsWith(path)`, which lights up EVERY
 * ancestor entry at once. Standing on `/complaint-management/service-jobs/board` matched
 * both "Dispatch Board" and "Service Jobs", because one path is a literal prefix of the
 * other - so the sidebar claimed you were in two places.
 *
 * Two rules fix it, and both are needed:
 *
 * 1. **Match on segment boundaries.** `/foo/bar-baz` must not match `/foo/bar`. A raw
 *    `startsWith` says it does, which is how a route highlights an unrelated sibling that
 *    merely shares a name prefix.
 * 2. **The longest match wins.** A detail page like `/complaints/{id}` SHOULD light up
 *    "Complaints" - there is no better entry for it. But when a more specific entry also
 *    matches, only that one is the current page. This is the part a per-item predicate
 *    cannot decide alone, which is why the matcher is built from the whole menu at once.
 */

/** Split a route into its segments, ignoring query and hash. */
function segments(path: string): string[] {
  return path.split(/[?#]/)[0].split('/').filter(Boolean);
}

/** True when `path` is `candidate` or one of its ancestors, on segment boundaries. */
export function isSegmentPrefix(path: string, candidate: string): boolean {
  const target = segments(path);
  const current = segments(candidate);
  if (target.length === 0) return current.length === 0;
  if (target.length > current.length) return false;
  return target.every((part, index) => part === current[index]);
}

/**
 * Build the predicate a menu asks per item.
 *
 * `allPaths` is every path in the rendered menu. Anything missing from it simply cannot
 * win the longest-match comparison, so a caller that forgets one degrades to the old
 * ancestor-matching behaviour for that entry rather than breaking.
 */
export function createMatchPath(
  pathname: string,
  allPaths: Iterable<string>,
): (path: string) => boolean {
  const candidates = Array.from(allPaths).filter((path) => isSegmentPrefix(path, pathname));
  const deepest = candidates.reduce(
    (best, path) => (segments(path).length > segments(best).length ? path : best),
    candidates[0] ?? '',
  );

  return (path: string): boolean => {
    if (path === pathname) return true;
    if (!isSegmentPrefix(path, pathname)) return false;
    // A deeper entry exists for this URL, so it - not this one - is the current page.
    return deepest === '' || path === deepest;
  };
}

/** Every `path` in a menu tree, including nested children. */
export function collectMenuPaths(
  items: ReadonlyArray<{ path?: string; children?: ReadonlyArray<unknown> }>,
): string[] {
  const out: string[] = [];
  const walk = (nodes: ReadonlyArray<{ path?: string; children?: ReadonlyArray<unknown> }>) => {
    for (const node of nodes) {
      if (node?.path) out.push(node.path);
      if (Array.isArray(node?.children)) {
        walk(node.children as ReadonlyArray<{ path?: string; children?: ReadonlyArray<unknown> }>);
      }
    }
  };
  walk(items);
  return out;
}
