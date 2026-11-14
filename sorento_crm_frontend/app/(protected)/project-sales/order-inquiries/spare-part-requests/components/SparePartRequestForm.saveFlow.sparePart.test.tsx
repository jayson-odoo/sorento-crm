/**
 * SPARE-PART-ORDER-REQUEST fix round 2, red-first (review S1 + S9).
 *
 * R2 (S1) New form: Submit saves (POST) then submits; when the submit is refused (422, e.g. no
 * approval stage), the form KEEPS the created draft's id and its new row ids, so the next
 * Submit / Save updates that draft (PUT /spare-part-requests/<id>, lines carrying their ids) and
 * never POSTs a second draft.
 * R7 (S9) Edit form: while the request loads it shows a loading state and Save / Submit are
 * disabled (or absent); a load error shows the error with "Try again" (which refetches); Save
 * can never send an empty lines list because the load had not finished.
 *
 * Asserted at the HTTP seam (`apiFetch`). `SearchableSelect` is stubbed to a native select (the
 * real one is an async popover jsdom cannot drive); its contract (value / onChange /
 * onOptionChange / options / fetchOptions) is unchanged.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

type Call = { url: string; method: string; body: unknown };
const calls: Call[] = [];
let handler: (url: string, method: string) => Response | Promise<Response>;

const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });

const SAVED = {
  id: 'spr-1',
  inquiry_no: 'OI-2611-0009',
  inquiry_type: 'spare_part_request',
  state: 'draft',
  currency: 'MYR',
  needed_by: null,
  default_location: null,
  reason: null,
  can_edit: true,
  can_decide: false,
  total: '50',
  lines: [
    {
      id: 'row-1',
      product_id: 'prod-1',
      item_code: 'SP-SEAL-40',
      product_name: 'Pump seal',
      description: 'Pump seal',
      stock_location: 'BRW',
      qty: '2',
      unit_price: '25',
      total: '50',
      requested_qty: null,
      requested_unit_price: null,
      state: 'draft',
    },
  ],
};

const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch {
      /* keep */
    }
  }
  calls.push({ url, method, body });
  return handler(url, method);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import * as FormModule from './SparePartRequestForm';

const SparePartRequestForm = ((FormModule as Record<string, unknown>).SparePartRequestForm ??
  (FormModule as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>>;

const SPR = '/api/v1/project-sales/spare-part-requests';
const writes = () => calls.filter((c) => c.url.startsWith(SPR) && c.method !== 'GET');

function mount(props: Record<string, unknown> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestForm {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe('R2 / S1: a refused submit never creates a second draft', () => {
  beforeEach(() => {
    handler = (url, method) => {
      if (url === SPR && method === 'POST') return ok(SAVED, 201);
      if (url === `${SPR}/spr-1` && method === 'PUT') return ok(SAVED);
      if (url.endsWith('/submit'))
        return ok({ message: 'No approval stage is set up for spare part requests yet.', code: 'spr_no_stage' }, 422);
      return ok(url.includes('select') ? { data: [] } : []);
    };
  });

  async function fillOneLine() {
    fireEvent.change(await screen.findByLabelText('Product for line 1'), { target: { value: 'prod-1' } });
    fireEvent.change(screen.getByLabelText('Location for line 1'), { target: { value: 'BRW' } });
    fireEvent.change(screen.getByLabelText('Qty for line 1'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Unit price for line 1'), { target: { value: '25' } });
  }

  it('the second Submit PUTs the created draft with its row ids, never a second POST', async () => {
    mount();
    await fillOneLine();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/submit'))).toBe(true));

    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/submit')).length).toBe(2));

    const posts = writes().filter((c) => c.url === SPR && c.method === 'POST');
    expect(posts).toHaveLength(1);
    const put = writes().find((c) => c.method === 'PUT');
    expect(put?.url).toBe(`${SPR}/spr-1`);
    expect((put?.body as { lines: Array<{ id: string | null }> }).lines[0].id).toBe('row-1');
  });

  it('Save as draft after a refused submit updates the same draft', async () => {
    mount();
    await fillOneLine();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/submit'))).toBe(true));

    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(writes().length).toBe(3));
    expect(writes().filter((c) => c.url === SPR && c.method === 'POST')).toHaveLength(1);
    expect(writes()[2]).toMatchObject({ url: `${SPR}/spr-1`, method: 'PUT' });
  });
});

describe('R7 / S9: the Edit form never hangs and never saves an unloaded request', () => {
  it('while loading: a loading state, Save and Submit disabled, nothing written', async () => {
    handler = (url) =>
      url === `${SPR}/spr-1` ? new Promise<Response>(() => undefined) : ok(url.includes('select') ? { data: [] } : []);
    const { container } = mount({ id: 'spr-1' });

    await waitFor(() => expect(calls.some((c) => c.url === `${SPR}/spr-1`)).toBe(true));
    const loading =
      container.querySelector('[data-slot="skeleton"]') ??
      screen.queryByRole('status') ??
      screen.queryByText(/loading/i);
    expect(loading).not.toBeNull();
    for (const name of ['Save as draft', 'Submit']) {
      const button = screen.queryByRole('button', { name });
      if (button) {
        expect(button).toBeDisabled();
        fireEvent.click(button);
      }
    }
    expect(writes()).toEqual([]);
  });

  it('a load error shows the error with Try again, which loads again', async () => {
    handler = (url) =>
      url === `${SPR}/spr-1`
        ? ok({ message: 'Spare part request not found' }, 404)
        : ok(url.includes('select') ? { data: [] } : []);
    mount({ id: 'spr-1' });

    const retry = await screen.findByRole('button', { name: /try again/i });
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    const before = calls.filter((c) => c.url === `${SPR}/spr-1`).length;
    fireEvent.click(retry);
    await waitFor(() =>
      expect(calls.filter((c) => c.url === `${SPR}/spr-1`).length).toBeGreaterThan(before),
    );
    expect(writes()).toEqual([]);
  });
});
