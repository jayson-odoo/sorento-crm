/** RANDOMUUID-HTTP: on a plain-http origin crypto.randomUUID is undefined; Filters must still open. */
import React from 'react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('@/lib/list-query/listQueryService', () => ({
  fetchListQueryFieldOptions: vi.fn(async () => ({ data: [] })),
  fetchListQueryFields: vi.fn(async () => [
    {
      field_key: 'total',
      label: 'Total',
      data_type: 'number',
      compile_key: 'total',
      allowed_operators: ['gt'],
      filterable: true,
      exportable: true,
      is_line_field: false,
      sort_order: 1,
    },
  ]),
}));

import { ListQueryFilterDialog } from './ListQueryFilterDialog';

describe('ListQueryFilterDialog without crypto.randomUUID (insecure context)', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('opens with a default condition and can add another', async () => {
    const real = globalThis.crypto;
    vi.stubGlobal('crypto', { getRandomValues: real.getRandomValues.bind(real) });
    expect((globalThis.crypto as { randomUUID?: unknown }).randomUUID).toBeUndefined();

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ListQueryFilterDialog
          resourceKey={'orders' as never}
          open
          onOpenChange={vi.fn()}
          initialFilter={null}
          onApply={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findAllByPlaceholderText('Value')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
    expect(await screen.findAllByPlaceholderText('Value')).toHaveLength(2);
  });
});
