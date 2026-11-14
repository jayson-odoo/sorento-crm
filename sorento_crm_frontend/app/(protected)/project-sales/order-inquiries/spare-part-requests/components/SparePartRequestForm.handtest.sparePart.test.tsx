/**
 * SPARE-PART-ORDER-REQUEST hand-test round (owner 13 Nov), red-first (Phase 2).
 * Contract: UAC "Hand-test round" G1, G2, G4.
 *
 * F1 (G1) the line table has a Description column; picking a product prefills it with the
 *    product's name; it stays editable and is sent in the payload.
 * F2 (G2) after Save as draft and after Submit the router goes to the request's own record
 *    page, /procurement-management/spare-part-requests/<id>, never /project-sales/order-inquiries.
 * F5 (G4) on the Create page a line's paperclip is there before the first save; the files picked
 *    there upload to /order-inquiry-rows/<row id>/attachments right after the first save.
 *
 * Asserted at the HTTP seam (`apiFetch`). `SearchableSelect` is stubbed to a native select that
 * loads its options through the real `fetchOptions` (so the product option is whatever the form's
 * own product search builds from /master-data/products/select).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const push = vi.fn();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace, back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/procurement-management/spare-part-requests/new',
  useSearchParams: () => new URLSearchParams(''),
  useParams: () => ({}),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissionSet: new Set(), permissions: [], isLoading: false, isError: false }),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));

vi.mock('@/components/common/SearchableSelect', async () => {
  const ReactMod = await import('react');
  type Option = { value: string; label: string };
  const SearchableSelect = (props: {
    'aria-label'?: string;
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    onOptionChange?: (o: Option | null) => void;
    options?: Option[];
    fetchOptions?: (q: string, page: number) => Promise<Option[]>;
    placeholder?: string;
  }) => {
    const [loaded, setLoaded] = ReactMod.useState<Option[]>([]);
    const { fetchOptions } = props;
    ReactMod.useEffect(() => {
      if (fetchOptions) void fetchOptions('', 0).then((o) => setLoaded(o ?? []));
    }, [fetchOptions]);
    const options: Option[] = fetchOptions
      ? loaded
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

const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });

const SPR = '/api/v1/project-sales/spare-part-requests';
const ROWS = '/api/v1/project-sales/order-inquiry-rows';
const RECORD = '/procurement-management/spare-part-requests/spr-1';

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
  can_revise: false,
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

function handler(url: string, method: string): Response {
  if (url.includes('/master-data/products/select'))
    return ok({ data: [{ id: 'prod-1', product_code: 'SP-SEAL-40', product_name: 'Pump seal' }] });
  if (url === SPR && method === 'POST') return ok(SAVED, 201);
  if (url === `${SPR}/spr-1` && method === 'PUT') return ok(SAVED);
  if (url === `${SPR}/spr-1/submit`) return ok({ ...SAVED, state: 'pending_approval' });
  if (url === `${SPR}/spr-1`) return ok(SAVED);
  if (url.endsWith('/attachments/lookup')) return ok({});
  if (url.startsWith(ROWS) && url.endsWith('/attachments') && method === 'POST') return ok([]);
  return ok(url.includes('select') ? { data: [] } : []);
}

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
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a),
}));

import * as FormModule from './SparePartRequestForm';

const SparePartRequestForm = ((FormModule as Record<string, unknown>).SparePartRequestForm ??
  (FormModule as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>>;

function mount(props: Record<string, unknown> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestForm {...props} />
    </QueryClientProvider>,
  );
}

async function pickProduct() {
  const select = (await screen.findByLabelText('Product for line 1')) as HTMLSelectElement;
  await waitFor(() => expect(select.querySelector('option[value="prod-1"]')).not.toBeNull());
  fireEvent.change(select, { target: { value: 'prod-1' } });
}

async function fillOneLine() {
  await pickProduct();
  fireEvent.change(screen.getByLabelText('Location for line 1'), { target: { value: 'BRW' } });
  fireEvent.change(screen.getByLabelText('Qty for line 1'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Unit price for line 1'), { target: { value: '25' } });
}

const descriptionInput = () =>
  screen.getByLabelText(/^description for line 1$/i) as HTMLInputElement | HTMLTextAreaElement;

const navigatedTo = () => [...push.mock.calls, ...replace.mock.calls].map((c) => String(c[0]));

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe('F1 (G1): a Description per line, prefilled from the product', () => {
  it('the line table has a Description column', async () => {
    mount();
    await screen.findByLabelText('Product for line 1');
    expect(screen.getByRole('columnheader', { name: 'Description' })).toBeInTheDocument();
  });

  it('picking a product prefills the description with the product name', async () => {
    mount();
    await pickProduct();
    await waitFor(() => expect(descriptionInput().value).toBe('Pump seal'));
  });

  it('the description stays editable and is sent in the payload', async () => {
    mount();
    await fillOneLine();
    await waitFor(() => expect(descriptionInput().value).toBe('Pump seal'));
    fireEvent.change(descriptionInput(), { target: { value: 'Pump seal, left side' } });
    expect(descriptionInput().value).toBe('Pump seal, left side');

    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(calls.some((c) => c.url === SPR && c.method === 'POST')).toBe(true));
    const post = calls.find((c) => c.url === SPR && c.method === 'POST');
    const lines = (post?.body as { lines: Array<{ description?: string | null }> }).lines;
    expect(lines[0].description).toBe('Pump seal, left side');
  });
});

describe('F2 (G2): Save as draft and Submit stay on the spare part request', () => {
  it('Save as draft goes to the request record page', async () => {
    mount();
    await fillOneLine();
    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(navigatedTo().length).toBeGreaterThan(0));
    expect(navigatedTo()[0]).toBe(RECORD);
    expect(navigatedTo().some((u) => u.startsWith('/project-sales/order-inquiries'))).toBe(false);
  });

  it('Submit goes to the request record page', async () => {
    mount();
    await fillOneLine();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(calls.some((c) => c.url === `${SPR}/spr-1/submit`)).toBe(true));
    await waitFor(() => expect(navigatedTo().length).toBeGreaterThan(0));
    expect(navigatedTo()[0]).toBe(RECORD);
    expect(navigatedTo().some((u) => u.startsWith('/project-sales/order-inquiries'))).toBe(false);
  });

  it('Save on the Edit form goes to the request record page', async () => {
    mount({ id: 'spr-1' });
    const save = await screen.findByRole('button', { name: 'Save as draft' });
    await waitFor(() => expect(save).not.toBeDisabled());
    fireEvent.click(save);
    await waitFor(() => expect(navigatedTo().length).toBeGreaterThan(0));
    expect(navigatedTo()[0]).toBe(RECORD);
  });
});

describe('F5 (G4): photos on the Create page upload on the first save', () => {
  it('a line paperclip is there before the first save', async () => {
    mount();
    await pickProduct();
    expect(screen.getByRole('button', { name: /^Attachments for Line 1/ })).toBeInTheDocument();
  });

  it('files picked before the first save upload to the created row right after it', async () => {
    mount();
    await fillOneLine();
    fireEvent.click(screen.getByRole('button', { name: /^Attachments for Line 1/ }));

    const dialog = await screen.findByRole('dialog');
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(input).not.toBeNull();
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'seal.png', { type: 'image/png' });
    fireEvent.change(input!, { target: { files: [file] } });
    // Whatever confirms the pick (Add / Upload / Done) is pressed if there is one; no upload
    // may go out yet: the row does not exist.
    const confirm = within(dialog)
      .queryAllByRole('button')
      .find((b) => /^(add|upload|attach|done|keep)/i.test(b.textContent?.trim() ?? '') && !b.hasAttribute('disabled'));
    if (confirm) fireEvent.click(confirm);
    if (screen.queryByRole('dialog')) fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(calls.some((c) => c.url.startsWith(ROWS) && /\/attachments$/.test(c.url))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Save as draft', hidden: true }));

    await waitFor(() =>
      expect(
        calls.some((c) => c.url === `${ROWS}/row-1/attachments` && c.method === 'POST'),
      ).toBe(true),
    );
    const createAt = calls.findIndex((c) => c.url === SPR && c.method === 'POST');
    const uploadAt = calls.findIndex((c) => c.url === `${ROWS}/row-1/attachments` && c.method === 'POST');
    expect(createAt).toBeGreaterThanOrEqual(0);
    expect(uploadAt).toBeGreaterThan(createAt);
    const form = calls[uploadAt].body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect((form.getAll('files') as File[]).map((f) => f.name)).toEqual(['seal.png']);
  });
});
