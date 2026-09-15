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

export function renderWithQueryClient(
  ui: ReactElement,
  options?: RenderOptions,
): RenderResult {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
    options,
  );
}
