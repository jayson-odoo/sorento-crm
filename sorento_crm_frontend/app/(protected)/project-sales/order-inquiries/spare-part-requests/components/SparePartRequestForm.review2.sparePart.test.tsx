/**
 * SPARE-PART-ORDER-REQUEST review round 2 (review S1, S3 a/b), red-first (Phase 2).
 * Contract: UAC "Hand-test round" G4 ("no lost files") and G5 (a pending edit restarts approval).
 *
 * R4 (S1) a photo held on a line with no product yet: Save as draft is refused with a plain
 *    message next to that line, the files stay held, nothing says "Saved as draft" and the page
 *    does not leave the form (today body() drops the product-less line and uploadHeld skips
 *    its files while still reporting success).
 * R6a (S3 a) a held upload that fails after the first save: the error is shown, the form stays,
 *    the files stay held, and the next Save retries exactly those files (one more upload POST
 *    to the same row, no second create). GUARD if green.
 * R6b (S3 b) Submit while editing a pending request: the save (PUT) is the restart, so there is
 *    no POST /submit, the toast says "Submitted again for approval" and the page opens the
 *    record. GUARD if green.
 *
 * Harness copied from SparePartRequestForm.handtest.sparePart.test.tsx (HTTP seam, `apiFetch`),
 * with a per-test answer override and an inspectable toast.
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
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));
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

/** Per-test override (null = the default handler below). */
let override: ((url: string, method: string) => Response | null) | null = null;
/** The state the Edit form's GET answers with. */
let loadedState = 'draft';

function handler(url: string, method: string): Response {
  const custom = override?.(url, method);
  if (custom) return custom;
  if (url === `${SPR}/spr-1` && method === 'GET') return ok({ ...SAVED, state: loadedState });
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
  override = null;
  loadedState = 'draft';
});

/** Pick a file in a line's Attachments dialog and close it (the F5 sequence). */
async function holdPhoto(lineNo: number, name = 'seal.png') {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Attachments for Line ${lineNo}`) }));
  const dialog = await screen.findByRole('dialog');
  const input = dialog.querySelector('input[type="file"]') as HTMLInputElement | null;
  expect(input, 'the held-files dialog has a file input').not.toBeNull();
  const file = new File([new Uint8Array([137, 80, 78, 71])], name, { type: 'image/png' });
  fireEvent.change(input!, { target: { files: [file] } });
  const confirm = within(dialog)
    .queryAllByRole('button')
    .find(
      (b) =>
        /^(add|upload|attach|done|keep)/i.test(b.textContent?.trim() ?? '') &&
        !b.hasAttribute('disabled'),
    );
  if (confirm) fireEvent.click(confirm);
  if (screen.queryByRole('dialog')) fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
}

const uploads = (rowId = 'row-1') =>
  calls.filter((c) => c.url === `${ROWS}/${rowId}/attachments` && c.method === 'POST');
const settle = () => new Promise((resolve) => setTimeout(resolve, 150));

describe('R4 (S1): a held photo on a line with no product is never dropped in silence', () => {
  it('Save as draft is refused next to that line; the files stay; no "Saved as draft"', async () => {
    mount();
    await fillOneLine();
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    await screen.findByLabelText('Product for line 2');
    await holdPhoto(2);

    fireEvent.click(screen.getByRole('button', { name: 'Save as draft', hidden: true }));
    await settle();
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    await settle();

    expect(
      toast.success.mock.calls.map((c) => String(c[0])),
      'never "Saved as draft" while a photo would be lost',
    ).not.toContain('Saved as draft');
    expect(navigatedTo(), 'the page stays on the form').toEqual([]);
    const row2 = screen.getByLabelText('Product for line 2').closest('tr') as HTMLElement;
    const next = row2.nextElementSibling as HTMLElement | null;
    const near = `${row2.textContent ?? ''} ${next?.textContent ?? ''}`;
    expect(near, 'a plain message next to line 2').toMatch(/choose a product/i);
    expect(
      screen.getByRole('button', { name: /^Attachments for Line 2/ }),
      'line 2 still holds its files',
    ).toBeInTheDocument();
  });
});

describe('R6a (S3 a): a failed held upload keeps the files for a retry', () => {
  it('shows the error, stays on the form, and the next Save re-sends the held files', async () => {
    let failNext = true;
    override = (url, method) => {
      if (url === `${ROWS}/row-1/attachments` && method === 'POST' && failNext) {
        failNext = false;
        return ok({ message: 'The file store is not reachable.', detail: null, code: null }, 400);
      }
      return null;
    };
    mount();
    await fillOneLine();
    await holdPhoto(1);

    fireEvent.click(screen.getByRole('button', { name: 'Save as draft', hidden: true }));
    await waitFor(() => expect(uploads().length).toBe(1));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error).toHaveBeenCalledWith('The file store is not reachable.');
    await settle();
    expect(navigatedTo(), 'the page stays on the form').toEqual([]);
    expect(toast.success.mock.calls.map((c) => String(c[0]))).not.toContain('Saved as draft');

    fireEvent.click(screen.getByRole('button', { name: 'Save as draft', hidden: true }));
    await waitFor(() => expect(uploads().length, 'the retry uploads again').toBe(2));
    const retried = uploads()[1].body as FormData;
    expect((retried.getAll('files') as File[]).map((f) => f.name)).toEqual(['seal.png']);
    expect(
      calls.filter((c) => c.url === SPR && c.method === 'POST').length,
      'the retry saves the same draft, never a second create',
    ).toBe(1);
    await waitFor(() => expect(navigatedTo()[0]).toBe(RECORD));
  });
});

describe('R6b (S3 b): Submit on a pending request saves straight back into approval', () => {
  it('PUTs the request, never POSTs /submit, says "Submitted again for approval"', async () => {
    loadedState = 'pending_approval';
    override = (url, method) =>
      url === `${SPR}/spr-1` && method === 'PUT' ? ok({ ...SAVED, state: 'pending_approval' }) : null;
    mount({ id: 'spr-1' });
    const submit = await screen.findByRole('button', { name: 'Submit' });
    await waitFor(() => expect(submit).not.toBeDisabled());
    fireEvent.click(submit);

    await waitFor(() => expect(calls.some((c) => c.url === `${SPR}/spr-1` && c.method === 'PUT')).toBe(true));
    await waitFor(() => expect(navigatedTo().length).toBeGreaterThan(0));
    expect(calls.some((c) => c.url === `${SPR}/spr-1/submit`), 'no POST /submit').toBe(false);
    expect(toast.success).toHaveBeenCalledWith('Submitted again for approval');
    expect(navigatedTo()[0]).toBe(RECORD);
  });
});
