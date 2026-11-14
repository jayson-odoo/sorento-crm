/**
 * Keep a list's filters in the address bar without a navigation (a shareable view): set each
 * given param, drop the ones given empty, keep every other param as it is.
 */
export function replaceUrlSearch(next: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  for (const [key, value] of Object.entries(next)) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  const search = params.toString();
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${search ? `?${search}` : ''}`,
  );
}
