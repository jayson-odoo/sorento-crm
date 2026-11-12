/**
 * SPARE-PART-ORDER-REQUEST fix round 6 (browser pass 3, row a3), red-first.
 *
 * At 375 px the create form page measured 797 px wide: the lines table's Actions header carries
 * an `sr-only` label, which is `position: absolute`, and with no positioned ancestor its
 * containing block is the page, so it escapes the table's `overflow-x-auto` scroller and widens
 * the page. The scroller must be a positioned containing block (`relative`), so every `sr-only`
 * inside the table is clipped by it.
 *
 * Harness copied from `SparePartRequestForm.fix5.sparePart.test.tsx` (jsdom cannot measure
 * layout, so the rule is asserted on the classes that decide it).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
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

const FIXED = /(?:^|\s)(?:min-)?w-\[(\d+)px\]/;

function mount() {
  cleanup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestForm />
    </QueryClientProvider>,
  );
}

describe('a3: no sr-only label inside the lines table can widen the page', () => {
  it('the lines table scroller is a positioned containing block (relative)', async () => {
    mount();
    const table = (await screen.findByLabelText('Qty for line 1')).closest('table') as HTMLElement;
    const scroller = table.parentElement?.closest('.overflow-x-auto') as HTMLElement | null;
    expect(scroller, 'an overflow-x-auto wrapper around the lines table').not.toBeNull();
    expect(table.querySelectorAll('.sr-only').length, 'the table carries an sr-only label').toBeGreaterThan(0);
    expect(scroller!.className, 'the scroller contains its absolutely positioned children').toMatch(
      /\b(relative|absolute|fixed|sticky)\b/,
    );
  });
});
