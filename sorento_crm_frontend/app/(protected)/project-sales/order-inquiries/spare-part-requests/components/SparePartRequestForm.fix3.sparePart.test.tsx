/**
 * SPARE-PART-ORDER-REQUEST fix round 3, B4 (browser pass), the form's half: a line total and the
 * request total on the New form read exactly as the shared `formatMoneyExact` renders them for
 * the request currency (MYR here), the same string the Lines tab and Approve popup print
 * (`[id]/components/moneyFormat.fix3.sparePart.test.tsx`). SearchableSelect stubbed as in
 * `SparePartRequestForm.saveFlow.sparePart.test.tsx`.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.fn();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace, back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/spare-part-requests/new',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissionSet: new Set(), permissions: [], isLoading: false, isError: false }),
}));

const PRODUCT = { value: 'prod-1', label: 'SP-SEAL-40 · Pump seal' };
vi.mock('@/components/common/SearchableSelect', () => {
  type Option = { value: string; label: string };
  const SearchableSelect = (props: {
    'aria-label'?: string;
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    onOptionChange?: (o: Option | null) => void;
    options?: Option[];
    fetchOptions?: unknown;
    placeholder?: string;
  }) => {
    const options: Option[] = props.fetchOptions
      ? [PRODUCT]
      : [...(props.options ?? []), { value: 'BRW', label: 'BRW' }];
    return (
      // eslint-disable-next-line no-restricted-syntax -- test stub standing in for SearchableSelect
      <select
        aria-label={props['aria-label'] ?? props.id ?? props.placeholder}
        value={props.value ?? ''}
        onChange={(event) => {
          const picked = options.find((o) => o.value === event.target.value) ?? null;
          props.onChange?.(event.target.value);
          props.onOptionChange?.(picked);
        }}
      >
        <option value="">-</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  };
  return { SearchableSelect, default: SearchableSelect };
});

const apiFetch = vi.fn(
  async (url: string) =>
    new Response(JSON.stringify(url.includes('select') ? { data: [] } : []), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string]) => apiFetch(...a) }));

import * as FormModule from './SparePartRequestForm';
import { formatMoneyExact } from '../../../_shared/lib/money';

const SparePartRequestForm = ((FormModule as Record<string, unknown>).SparePartRequestForm ??
  (FormModule as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>>;

describe('B4: the form prints money through the shared formatter', () => {
  it('a line of 4 x 35 reads formatMoneyExact("140", MYR), and so does the request total', async () => {
    cleanup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SparePartRequestForm />
      </QueryClientProvider>,
    );
    fireEvent.change(await screen.findByLabelText('Product for line 1'), { target: { value: 'prod-1' } });
    fireEvent.change(screen.getByLabelText('Location for line 1'), { target: { value: 'BRW' } });
    fireEvent.change(screen.getByLabelText('Qty for line 1'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Unit price for line 1'), { target: { value: '35' } });

    const expected = formatMoneyExact('140.0000', 'MYR');
    await waitFor(() => expect(screen.getAllByText(new RegExp(expected.replace('.', '\\.'))).length).toBeGreaterThan(0));
    const row = screen.getByLabelText('Qty for line 1').closest('tr') as HTMLElement;
    expect(row.textContent ?? '').toContain(expected);
  });
});
