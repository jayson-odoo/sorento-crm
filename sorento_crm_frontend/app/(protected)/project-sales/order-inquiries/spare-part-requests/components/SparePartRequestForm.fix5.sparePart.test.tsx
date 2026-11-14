/**
 * SPARE-PART-ORDER-REQUEST fix round 5 (browser pass 2), D4: the create form at 375 px never
 * scrolls the PAGE sideways (pass 2 measured scrollWidth 797 at 375: the lines table's fixed
 * min width leaked). jsdom has no layout, so the contract is asserted on the classes that decide
 * it: the lines table sits in its own `overflow-x-auto` scroller; nothing OUTSIDE that scroller
 * carries a fixed pixel width or min width wider than the 375 viewport; the form root, and every
 * flex / grid item between it and the scroller, can shrink (`min-w-0`), since a flex or grid item
 * defaults to `min-width: auto` and is pushed out by the table's own min width otherwise.
 * SearchableSelect stubbed as in `SparePartRequestForm.saveFlow.sparePart.test.tsx`.
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

describe('D4: the create form at 375 px scrolls the lines table, never the page', () => {
  it('the lines table has its own overflow-x-auto scroller', async () => {
    const { container } = mount();
    const table = (await screen.findByLabelText('Qty for line 1')).closest('table') as HTMLElement;
    const scroller = table.parentElement?.closest('.overflow-x-auto');
    expect(scroller, 'an overflow-x-auto wrapper around the lines table').not.toBeNull();
    expect(container.contains(scroller as Node)).toBe(true);
  });

  it('nothing outside that scroller is fixed wider than the viewport', async () => {
    const { container } = mount();
    const table = (await screen.findByLabelText('Qty for line 1')).closest('table') as HTMLElement;
    const scroller = table.parentElement?.closest('.overflow-x-auto') as HTMLElement | null;
    const leaks = Array.from(container.querySelectorAll<HTMLElement>('[class]'))
      .filter((el) => !(scroller && scroller.contains(el)))
      .map((el) => ({ el, m: FIXED.exec(el.getAttribute('class') ?? '') }))
      .filter(({ m }) => m && Number(m[1]) > 375)
      .map(({ el, m }) => `${el.tagName.toLowerCase()} ${m![0].trim()}`);
    expect(leaks).toEqual([]);
  });

  it('the form root and every flex / grid item above the scroller can shrink (min-w-0)', async () => {
    const { container } = mount();
    const table = (await screen.findByLabelText('Qty for line 1')).closest('table') as HTMLElement;
    const root = container.firstElementChild as HTMLElement;
    expect(root.className, 'the form root').toMatch(/\bmin-w-0\b/);
    const stuck: string[] = [];
    for (let el = table.parentElement; el && el !== root; el = el.parentElement) {
      const parent = el.parentElement;
      const parentLays = /\b(flex|grid|inline-flex|inline-grid)\b/.test(parent?.className ?? '');
      if (parentLays && !/\bmin-w-0\b/.test(el.className)) stuck.push(`${el.tagName.toLowerCase()}.${el.className}`);
    }
    expect(stuck).toEqual([]);
  });
});
