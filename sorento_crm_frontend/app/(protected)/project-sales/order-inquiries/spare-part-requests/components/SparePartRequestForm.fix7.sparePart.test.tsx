/**
 * SPARE-PART-ORDER-REQUEST fix round 7 (owner standing rule), red-first.
 *
 * Rows carry no action icon buttons and no dedicated Remove button: a line is removed through
 * its row menu, a right-click (a long press on touch), the way the quotation lines grid does
 * (`QuotationLinesGrid.tsx`, `components/ui/context-menu`). The paperclip and the stock expand
 * stay on the row.
 *
 * Harness copied from `SparePartRequestForm.fix6.sparePart.test.tsx`.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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

const SparePartRequestForm = ((FormModule as Record<string, unknown>).SparePartRequestForm ??
  (FormModule as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>>;

function mount() {
  cleanup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestForm />
    </QueryClientProvider>,
  );
}

describe('owner rule: a line is removed from its row menu, never a row button', () => {
  it('no row renders a Remove line button', async () => {
    mount();
    await screen.findByLabelText('Qty for line 1');
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    await screen.findByLabelText('Qty for line 2');
    expect(screen.queryAllByRole('button', { name: /remove line/i })).toHaveLength(0);
  });

  it('right-clicking a row offers Remove line, which removes that row only', async () => {
    mount();
    fireEvent.change(await screen.findByLabelText('Qty for line 1'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    const second = await screen.findByLabelText('Qty for line 2');
    fireEvent.change(second, { target: { value: '7' } });

    fireEvent.contextMenu(second.closest('tr') as HTMLElement);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove line' }));

    expect(screen.queryByLabelText('Qty for line 2')).toBeNull();
    expect((screen.getByLabelText('Qty for line 1') as HTMLInputElement).value).toBe('3');
  });
});
