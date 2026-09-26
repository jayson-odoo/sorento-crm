/**
 * The react-query wrapper every designer spec renders through.
 *
 * `RequestTagDesigner` grew a deferred tag Remove (`useDeferredRowAction`), which
 * is a react-query mutation - so a bare `render(<RequestTagDesigner .../>)` now
 * throws "No QueryClient set" before anything on the page exists, and the
 * failure names react-query rather than the component under test.
 *
 * `retry: false` so a rejected query surfaces on the first tick instead of being
 * retried three times past the end of the test, which is the same reason
 * `PromotionTypesList.test.tsx` sets it.
 */
import React, { type ReactElement } from 'react';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/** One client factory, so a hook test and a component test build the exact
 *  same defaults (`retry: false`) and never drift apart. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

/**
 * `queryClient` rides along on the return value (additive - every existing
 * destructure of a `RenderResult` field is untouched) so a poll-driven test
 * can push new data into the cache (`invalidateQueries`) without remounting
 * the component under test, which is the whole point of testing a poll.
 */
export function renderWithQueryClient(
  ui: ReactElement,
  options?: RenderOptions & { queryClient?: QueryClient },
): RenderResult & { queryClient: QueryClient } {
  const { queryClient: provided, ...renderOptions } = options ?? {};
  const client = provided ?? createTestQueryClient();
  const result = render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
    renderOptions,
  );
  return { ...result, queryClient: client };
}
