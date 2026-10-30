/**
 * PORTAL-P4-REQUESTS: the salesperson's CRM create / edit page renders the PORTAL form, and that form
 * refuses to submit while a required field is empty. The server does not yet enforce it (lane
 * FORM-REQUIRED-SERVER), so this UI refusal is the only gate today and is pinned per kind.
 *
 * The real MyRequestPortalForm -> SubmissionForm over a fake my-requests API; a draft with every field
 * filled except one required field is opened, Submit is confirmed, and no `/submit` call may be sent.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  CMP_DETAIL,
  PR_DETAIL,
  SF_DETAIL,
  SI_DETAIL,
  createCrmApi,
} from '@/app/(auth)/portal/components/__fixtures__/crmSubmissionApi';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(''),
}));
const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Ann Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/components/common/deferredToast', () => ({ deferredToast: vi.fn(() => 't'), dismissDeferredToast: vi.fn() }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

const detailRef: { current: Record<string, unknown> } = { current: {} };
let api = createCrmApi('stock_inquiry', () => detailRef.current);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => api.handler(...a) }));

import MyRequestPortalForm from '@/components/common/MyRequestPortalForm';

type Kind = 'stock_inquiry' | 'complaint' | 'purchase_request' | 'sponsorship_form';

const CASES: {
  kind: Kind;
  id: string;
  /** The required field left empty, as the form labels it. */
  field: string;
  detail: () => Record<string, unknown>;
}[] = [
  { kind: 'stock_inquiry', id: 'si-5', field: 'Salesperson', detail: () => SI_DETAIL({ salesperson_contact_id: '', salesperson: '' }) },
  {
    kind: 'complaint',
    id: 'cp-5',
    field: 'Defect description',
    detail: () =>
      CMP_DETAIL({
        customer_type: 'opt-a',
        within_warranty: 'opt-a',
        defects_discovered: 'opt-a',
        complaint_type: 'opt-a',
        defect_description: '',
      }),
  },
  { kind: 'purchase_request', id: 'pr-5', field: 'Requested by', detail: () => PR_DETAIL({ requested_by_contact_id: '', requested_by: '' }) },
  { kind: 'sponsorship_form', id: 'sf-5', field: 'Requested by', detail: () => SF_DETAIL({ requested_by_contact_id: '', requested_by: '' }) },
];

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => cleanup());

describe.each(CASES)('$kind: the CRM page (portal form) refuses a submit with "$field" empty', ({ kind, id, field, detail }) => {
  it('sends no submit request and shows the required-field message', async () => {
    detailRef.current = detail();
    api = createCrmApi(kind, () => detailRef.current);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MyRequestPortalForm kind={kind} submissionId={id} />
      </QueryClientProvider>,
    );

    const user = userEvent.setup();
    const open = await screen.findByRole('button', { name: /^Submit /i });
    await user.click(open);
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: /^Submit /i }));

    await waitFor(() => expect(toasts.error).toHaveBeenCalled());
    const message = String(toasts.error.mock.calls[0][0]);
    expect(message).toMatch(/Missing \d+ required field/);
    expect(message).toContain(field);

    expect(api.calls.filter((c) => c.method !== 'GET' && /\/submit$/.test(c.url.split('?')[0]))).toEqual([]);
    expect(api.calls.filter((c) => c.method === 'POST' || c.method === 'PUT' || c.method === 'PATCH')).toEqual([]);
  });
});
