/**
 * NPA-FROM-SI (owner 8 Nov 09:30): the NPA customer field is the stock inquiry's customer dropdown.
 * Same shared component (wrapper carries data-testid="customer-debtor-combobox") and the same option
 * source, `client.lookupDebtors(q, 20, undefined)` (GET /api/v1/public/portal/lookups/debtors, all
 * company customers), never `/new-product-application/customers`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
    <button onClick={() => onSelect?.()}>{children}</button>
  ),
}));
vi.mock('../lib/new-product-application-service', () => ({
  listMyRespondedInquiries: vi.fn(async () => []),
  getNewProductApplicationPrefill: vi.fn(),
  searchNewProductApplicationProducts: vi.fn(async () => []),
  getNewProductApplicationReuseSuggestions: vi.fn(async () => []),
  lookupNewProductApplication: vi.fn(async () => []),
  lookupNewProductApplicationCustomers: vi.fn(async () => []),
  downloadNewProductApplicationExcel: vi.fn(),
  createNewProductApplication: vi.fn(),
  updateNewProductApplication: vi.fn(),
  submitNewProductApplication: vi.fn(),
  reviseNewProductApplication: vi.fn(),
  cancelNewProductApplication: vi.fn(),
  getNewProductApplication: vi.fn(),
}));
vi.mock('./AttachmentDropzone', () => ({ AttachmentDropzone: () => null }));

import * as portalClient from '../lib/portal-client';
import { SubmissionClientProvider } from '../lib/submission-client';
import {
  createNewProductApplication,
  lookupNewProductApplicationCustomers,
} from '../lib/new-product-application-service';
import NewProductApplicationForm from './NewProductApplicationForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const lookupDebtors = vi.fn();

function mount() {
  const client = { ...portalClient, lookupDebtors };
  return render(
    <SubmissionClientProvider client={client as never}>
      <NewProductApplicationForm slug="acme" />
    </SubmissionClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  lookupDebtors.mockResolvedValue([
    { customer_id: 'd-1', debtor_name: 'ZZT Debtor', customer_code: 'D-1', sales_type: null },
  ]);
  asMock(createNewProductApplication).mockResolvedValue({ id: 'a-1', lines: [] });
});

async function typeInCustomer(text: string) {
  const box = await screen.findByLabelText('Customer');
  fireEvent.focus(box);
  fireEvent.change(box, { target: { value: text } });
  return box;
}

describe('portal NPA customer = the stock inquiry customer dropdown', () => {
  it('searches through client.lookupDebtors (all company customers), not the NPA customers lookup', async () => {
    mount();
    await typeInCustomer('ZZ');
    // The shared combobox (like the stock inquiry one) also fetches '' on focus: the typed search
    // is the call that matters, with the SI's exact arguments.
    await waitFor(() => expect(lookupDebtors.mock.calls.some((c) => c[0] === 'ZZ')).toBe(true));
    const typed = lookupDebtors.mock.calls.find((c) => c[0] === 'ZZ')!;
    expect(typed[1]).toBe(20);
    expect(typed[2]).toBeUndefined();
    expect(lookupNewProductApplicationCustomers).not.toHaveBeenCalled();
  });

  it('renders the shared customer combobox', async () => {
    mount();
    await screen.findByLabelText('Customer');
    expect(screen.getAllByTestId('customer-debtor-combobox')).toHaveLength(1);
  });

  it('picking a customer fills customer_id and customer_name on save', async () => {
    mount();
    await typeInCustomer('ZZ');
    const hit = await screen.findByText('ZZT Debtor');
    fireEvent.mouseDown(hit);
    fireEvent.click(hit);
    await waitFor(() =>
      expect((screen.getByLabelText('Customer') as HTMLInputElement).value).toBe('ZZT Debtor'),
    );
    expect(screen.queryByText('No debtor code')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() => expect(createNewProductApplication).toHaveBeenCalledTimes(1));
    const body = asMock(createNewProductApplication).mock.calls[0][0];
    expect(body.customer_id).toBe('d-1');
    expect(body.customer_name).toBe('ZZT Debtor');
  });

  it('free text is still allowed: no id, the typed name, and the No debtor code badge', async () => {
    mount();
    const box = await typeInCustomer('Walk-in Co');
    fireEvent.blur(box);
    expect(await screen.findByText('No debtor code')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() => expect(createNewProductApplication).toHaveBeenCalledTimes(1));
    const body = asMock(createNewProductApplication).mock.calls[0][0];
    expect(body.customer_id).toBeNull();
    expect(body.customer_name).toBe('Walk-in Co');
  });
});
