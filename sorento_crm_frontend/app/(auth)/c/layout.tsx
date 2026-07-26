import type { ReactNode } from 'react';

/**
 * Published catalogues render with no chrome at all.
 *
 * The `(auth)` group's default is `BrandedLayout`, which frames a sign-in card.
 * A consumer following a shared product link is not signing in to anything, so
 * this overrides it with a bare passthrough.
 */
export default function PublicCatalogueLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
