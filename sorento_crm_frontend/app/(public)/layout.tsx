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
 *
 * Leaving a group takes away what it GAVE as well as what it imposed, which is
 * what the stylesheet below is for.
 */

/**
 * Cancel the app shell. Not decoration: without it these pages are 274px wide.
 *
 * The root layout makes `<body>` a full-height flex ROW so the sidebar can sit
 * beside the content. Every route that supplies a sidebar is fine. These do
 * not, so the page's `<main>` is a lone flex item, and a flex item shrinks to
 * fit its contents rather than filling its parent. Measured on the running
 * build at 1400px: the catalogue's `<section className="w-full">` came back
 * 274px, two 107px tiles against the left edge of a blank page. `w-full` is no
 * defence, because it resolves against a parent that has already collapsed.
 *
 * `BrandedLayout` was hiding this. Its wrapper carried `flex grow w-full`, so
 * the catalogue inherited a usable width along with the sign-in card. Removing
 * the card removed the width too, and nothing said so until someone measured.
 *
 * Stated ONCE, here, rather than per page: the print route needs exactly the
 * same thing (a printed document is a block that flows onto as many pages as it
 * needs, not a flex item sized by a shell), and two copies of one rule drift.
 * `!important` is required because `.flex` and `.h-full` are class selectors
 * and these are element selectors, so the shell's utilities win on specificity.
 */
const RESET_CSS = `
html, body { display: block !important; height: auto !important; }
`;

export default function PublicCatalogueLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: RESET_CSS }} />
      {children}
    </>
  );
}
