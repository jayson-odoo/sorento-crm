/**
 * Dependency-free on purpose: `app/global-error.tsx` imports it, and that boundary
 * must share no chunk with the UI it stands in for (a failed chunk load is the
 * commonest way to land there).
 */
const CHUNK_FAILURE_PATTERNS = [
  /Loading (CSS )?chunk [\w-]+ failed/i, // webpack
  /Failed to load chunk/i, // turbopack
  /Failed to fetch dynamically imported module/i, // Chromium native import()
  /Importing a module script failed/i, // Safari native import()
  /error loading dynamically imported module/i, // Firefox native import()
];

/**
 * A chunk the browser asked for no longer exists on the server: the tab still runs
 * the previous build and a deploy replaced its chunks. Retrying the render cannot
 * fix that; only a full page load, which fetches the new build, can.
 */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  if (error.name === 'ChunkLoadError') return true;
  return CHUNK_FAILURE_PATTERNS.some((p) => p.test(error.message));
}

/** The commit this bundle was built from; `dev` when the build did not say. */
export function buildSha(): string {
  return process.env.NEXT_PUBLIC_BUILD_SHA || 'dev';
}

const RELOAD_KEY_PREFIX = 'sorento:chunk-reload:';

/**
 * Claim the one automatic reload this build gets in this tab. True means the caller
 * should reload now. False means this build already reloaded once (the reload did not
 * fix it), or sessionStorage is unavailable, in which case reloading could loop
 * forever, so the error screen shows instead.
 */
export function claimStaleChunkReload(sha: string = buildSha()): boolean {
  try {
    const key = RELOAD_KEY_PREFIX + sha;
    if (window.sessionStorage.getItem(key)) return false;
    window.sessionStorage.setItem(key, String(Date.now()));
    return window.sessionStorage.getItem(key) !== null;
  } catch {
    return false;
  }
}
