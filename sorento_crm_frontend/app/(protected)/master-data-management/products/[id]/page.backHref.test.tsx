/**
 * Product detail page - where Back goes (captain ruling 2026-08-17).
 *
 * A reviewer who opened a product from the spec verification worklist must land back
 * on that list, intact. The worklist hands its whole URL over in `back`; anything that
 * is not a relative path into the worklist falls through to the products list, because
 * a Back button that follows an arbitrary URL is an open redirect.
 */
import { Suspense, type ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act } from '@testing-library/react';

const nav = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => nav.params,
}));

// The record itself has its own suite; this test is about the toolbar's one link.
vi.mock('./components/ProductDetail', () => ({ default: () => null }));
// The shell container reads the app-wide settings provider this test does not mount.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

import ProductDetailPage from './page';

/** `params` is a promise the page `use()`s, so the first render suspends. */
async function renderPage() {
  await act(async () => {
    render(
      <Suspense fallback={null}>
        <ProductDetailPage params={Promise.resolve({ id: 'p-1' })} />
      </Suspense>,
    );
  });
}

beforeEach(() => {
  nav.params = new URLSearchParams();
});

afterEach(() => cleanup());

describe('Back link', () => {
  it('returns to the worklist, query and all, when `back` carries it', async () => {
    nav.params = new URLSearchParams({
      tab: 'specifications',
      back: '/master-data-management/spec-verification?state=unverified&page=3&selected=WC200&focus=WC100',
    });
    await renderPage();

    const link = screen.getByRole('link', {
      name: /Back to spec verification/,
    });
    expect(link).toHaveAttribute(
      'href',
      '/master-data-management/spec-verification?state=unverified&page=3&selected=WC200&focus=WC100',
    );
  });

  it('falls back to the products list when there is no `back`', async () => {
    nav.params = new URLSearchParams({ page: '2' });
    await renderPage();

    const link = screen.getByRole('link', { name: /Back to products/ });
    expect(link).toHaveAttribute(
      'href',
      '/master-data-management/products?page=2',
    );
  });

  it('ignores a `back` that points anywhere but the worklist', async () => {
    nav.params = new URLSearchParams({ back: 'https://evil.test/steal' });
    await renderPage();

    const link = screen.getByRole('link', { name: /Back to products/ });
    expect(link.getAttribute('href')).not.toContain('evil.test/steal');
  });

  it('ignores a protocol-relative `back`', async () => {
    nav.params = new URLSearchParams({ back: '//evil.test/steal' });
    await renderPage();

    const link = screen.getByRole('link', { name: /Back to products/ });
    expect(link.getAttribute('href')).not.toBe('//evil.test/steal');
  });
});
