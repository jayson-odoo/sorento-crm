/**
 * SPARE-PART-ORDER-REQUEST fix round 6, E2: labels in the spare part request form follow the owner
 * rule (`lib/product-display.ts` codeWithName: separator " - ", the name only when it differs
 * from the code). Never " · ", never the code twice:
 *   location 'DC1-BB' named 'DC1-BB' -> 'DC1-BB'; 'HQ' named 'HEADQUARTER' -> 'HQ - HEADQUARTER';
 *   product 'JC-PUMP' named 'JC-PUMP' -> 'JC-PUMP'; 'SP-SEAL' named 'Pump seal' -> 'SP-SEAL - Pump seal';
 *   a reopened draft line 'HINGES' named 'HINGES' -> 'HINGES'.
 * Data enters at the HTTP seam (`apiFetch`): /master-data/products/select, /inventory/warehouses,
 * GET /spare-part-requests/<id>. SearchableSelect is stubbed to print every option label it is
 * given (static `options`, or what `fetchOptions('', 0)` resolves) and its `selectedOption` label.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
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

vi.mock('@/components/common/SearchableSelect', async () => {
  const React = await import('react');
  type Option = { value: string; label: string };
  const SearchableSelect = (props: {
    'aria-label'?: string;
    id?: string;
    options?: Option[];
    fetchOptions?: (q: string, page?: number) => Promise<Option[]>;
    selectedOption?: Option;
    placeholder?: string;
  }) => {
    const { fetchOptions } = props;
    const [fetched, setFetched] = React.useState<Option[]>([]);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('', 0).then(setFetched);
    }, [fetchOptions]);
    const name = props['aria-label'] ?? props.id ?? props.placeholder ?? 'select';
    return (
      <div data-testid={`select:${name}`}>
        <span data-testid={`selected:${name}`}>{props.selectedOption?.label ?? ''}</span>
        <ul>
          {[...(props.options ?? []), ...fetched].map((o) => (
            <li key={o.value} data-testid="option-label">
              {o.label}
            </li>
          ))}
        </ul>
      </div>
    );
  };
  return { SearchableSelect, default: SearchableSelect };
});

const json = (b: unknown) =>
  new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });

const DRAFT = {
  id: 'spr-1',
  inquiry_no: 'OI-2611-0003',
  inquiry_type: 'spare_part_request',
  state: 'draft',
  currency: 'MYR',
  needed_by: null,
  default_location: 'HQ',
  reason: null,
  can_edit: true,
  can_decide: false,
  total: '0',
  lines: [
    { id: 'row-1', product_id: 'p9', item_code: 'HINGES', product_name: 'HINGES', description: 'HINGES',
      stock_location: 'DC1-BB', qty: '2', unit_price: '5', total: '10', requested_qty: null,
      requested_unit_price: null, state: 'draft' },
    { id: 'row-2', product_id: 'p2', item_code: 'SP-SEAL', product_name: 'Pump seal', description: 'Pump seal',
      stock_location: 'HQ', qty: '1', unit_price: '5', total: '5', requested_qty: null,
      requested_unit_price: null, state: 'draft' },
  ],
};

const apiFetch = vi.fn(async (url: string) => {
  if (url.includes('/master-data/products/select'))
    return json({
      data: [
        { id: 'p1', product_code: 'JC-PUMP', product_name: 'JC-PUMP' },
        { id: 'p2', product_code: 'SP-SEAL', product_name: 'Pump seal' },
      ],
    });
  if (url.includes('/inventory/warehouses'))
    return json({
      data: [
        { id: 'w1', warehouse_code: 'DC1-BB', warehouse_name: 'DC1-BB' },
        { id: 'w2', warehouse_code: 'HQ', warehouse_name: 'HEADQUARTER' },
      ],
    });
  if (url.includes('/spare-part-requests/spr-1')) return json(DRAFT);
  return json(url.includes('select') ? { data: [] } : []);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string]) => apiFetch(...a) }));

import * as FormModule from './SparePartRequestForm';

const SparePartRequestForm = ((FormModule as Record<string, unknown>).SparePartRequestForm ??
  (FormModule as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>>;

function mount(props: Record<string, unknown> = {}) {
  cleanup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestForm {...props} />
    </QueryClientProvider>,
  );
}

const labels = () => screen.queryAllByTestId('option-label').map((li) => (li.textContent ?? '').trim());

describe('E2: option labels follow codeWithName', () => {
  it('location options read "DC1-BB" and "HQ - HEADQUARTER"', async () => {
    mount();
    await waitFor(() => expect(labels()).toEqual(expect.arrayContaining(['DC1-BB', 'HQ - HEADQUARTER'])));
    expect(labels().filter((l) => l.includes(' · '))).toEqual([]);
    expect(labels()).not.toContain('DC1-BB · DC1-BB');
  });

  it('product options read "JC-PUMP" and "SP-SEAL - Pump seal"', async () => {
    mount();
    await waitFor(() => expect(labels()).toEqual(expect.arrayContaining(['JC-PUMP', 'SP-SEAL - Pump seal'])));
    expect(labels().filter((l) => l.includes(' · '))).toEqual([]);
  });
});

describe('E2: a reopened draft line reads its code once', () => {
  it('"HINGES" named "HINGES" reads "HINGES"; "SP-SEAL" reads "SP-SEAL - Pump seal"', async () => {
    mount({ id: 'spr-1' });
    const first = await screen.findByTestId('selected:Product for line 1', {}, { timeout: 5000 });
    await waitFor(() => expect((first.textContent ?? '').trim()).not.toBe(''));
    expect((first.textContent ?? '').trim()).toBe('HINGES');
    expect((screen.getByTestId('selected:Product for line 2').textContent ?? '').trim()).toBe(
      'SP-SEAL - Pump seal',
    );
  });
});
