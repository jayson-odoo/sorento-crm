import type { ReactNode } from 'react';

/**
 * Published catalogues, and the page headless Chromium prints: no chrome at all.
 *
 * These routes used to sit under `(auth)` with a bare passthrough layout at
 * `c/` that was meant to cancel that group's `BrandedLayout`. It cannot: in the
 * App Router a nested layout WRAPS its parent's, it never replaces it. So every
 * catalogue was really rendered inside the sign-in card - centred, `max-w-6xl`,
 * padded - and the PDF worker printed that card. Measured on an A4 render, the
 * document began 65pt in from the left edge and the last 64pt (23mm) of it,
 * including the right-hand tile, hung off the paper and was clipped.
 *
 * The only way out of a layout is out of its group, which is what this group is
 * for. Route groups do not appear in the URL, so `/c/...` is unchanged.
 */
export default function PublicCatalogueLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
