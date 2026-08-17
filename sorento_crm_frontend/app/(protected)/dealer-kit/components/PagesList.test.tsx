import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { PagesList } from './PagesList';
import { MOCK_PAGES } from '../__mocks__/fixtures';

/**
 * Component tests for the catalogue pages list.
 *
 * Scope note, stated rather than hidden: the shared `DataGridTable` does not
 * mount its row body under jsdom, so the populated and empty table states are
 * NOT asserted here - they would pass vacuously. Those live in
 * `e2e/dealer-kit-builder.spec.ts`, which renders the real grid and checks the
 * rows and their publish state against a running app.
 *
 * What is genuinely testable here is everything the component owns OUTSIDE the
 * grid body: the loading state, and the error path that must replace the table
 * entirely rather than leaving a blank one.
 */

// `vi.mock` factories are hoisted above module scope, so the spy has to be
// created inside `vi.hoisted` - a plain `const` above would still be in its
// temporal dead zone when the factory runs.
const { listPages } = vi.hoisted(() => ({ listPages: vi.fn() }));

vi.mock('../services/dealerKitService', () => ({ listPages }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <QueryClientProvider client={client}>
      <PagesList />
    </QueryClientProvider>,
  );
}

describe('PagesList', () => {
  beforeEach(() => {
    listPages.mockReset();
  });

  it('shows a loading state before the pages arrive', async () => {
    listPages.mockReturnValue(new Promise(() => {}));

    const { container } = renderList();

    await waitFor(() => {
      expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy();
    });
  });

  it('replaces the table with the failure instead of showing a blank one', async () => {
    listPages.mockRejectedValue(new Error('Backend unavailable'));

    const { container } = renderList();

    expect(await screen.findByText(/could not load pages/i)).toBeInTheDocument();
    expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument();
    // An error next to an empty grid reads as "no pages", which is a different
    // and much worse message than "we could not load them".
    expect(container.querySelector('[data-slot="card-table"]')).toBeNull();
  });

  it('keeps the search box usable while the request is still in flight', async () => {
    listPages.mockReturnValue(new Promise(() => {}));

    renderList();

    expect(await screen.findByRole('textbox', { name: /search pages/i })).toBeEnabled();
  });

  it('requests the page list exactly once per mount', async () => {
    listPages.mockResolvedValue(MOCK_PAGES);

    renderList();

    await waitFor(() => expect(listPages).toHaveBeenCalledTimes(1));
  });
});
