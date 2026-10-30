/**
 * QUOTE-CUSTOMER-AMEND, customer side: suggesting quantities and prices on the sign page
 * (AC-QCA-13, 14, 15, 30).
 *
 * Written BEFORE the UI exists (Phase 2, test-first), against the page #1987 reshaped: the
 * "Sign and accept" pad, the terms tick, no GPS. The page payload gains `lines[].id`,
 * `amendment_request`, `superseded_by_ref`, `can_sign` and `sign_blocked_reason`; the service gains
 * `submitAmendmentRequest(token, body)`. Every value here is invented.
 *
 * What these pin, from the approved mock v3 (documentation/mockups/QUOTE-CUSTOMER-AMEND):
 * the page's own nine columns plus ONE narrow icon column; Qty and Unit rate become inputs in
 * suggest mode; a staged removal is struck through; only changed lines are sent; Sign says why it
 * is off, once; an answered request shows its answers in the cells the customer changed.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationSignPage } from '../../services/quotationSignService';

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = vi.fn(
    () => null,
  ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});

const getQuotationSignPage = vi.fn();
const requestQuotationChanges = vi.fn();
const acceptQuotation = vi.fn();
const submitAmendmentRequest = vi.fn();

vi.mock('../../services/quotationSignService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/quotationSignService')>();
  return {
    ...actual,
    getQuotationSignPage: (...args: unknown[]) => getQuotationSignPage(...args),
    requestQuotationChanges: (...args: unknown[]) => requestQuotationChanges(...args),
    acceptQuotation: (...args: unknown[]) => acceptQuotation(...args),
    submitAmendmentRequest: (...args: unknown[]) => submitAmendmentRequest(...args),
  };
});

import { QuotationSignClient } from './QuotationSignClient';

// ------------------------------------------------------------------ fixtures

const OPEN_SENTENCE = 'You can sign once Sorento has answered your suggestions.';
const TICK_HINT = 'Tick to agree to the terms before you accept.';
const REPLACED = 'This quotation has been replaced by Quotation No. PRJQ-0000-R2.';

type Line = {
  id: string;
  item_label: string;
  description: string;
  technical_spec: string | null;
  brand: string | null;
  product_code: string;
  quantity: string;
  unit_price: string;
  complete_set: string | null;
  band_label: string | null;
  is_rate_only: boolean;
  amount: string | null;
};

function line(id: string, item: string, over: Partial<Line>): Line {
  return {
    id,
    item_label: item,
    description: `Item ${item}`,
    technical_spec: null,
    brand: 'BRAND-X',
    product_code: `ZZT-${item}`,
    quantity: '120',
    unit_price: '100.00',
    complete_set: null,
    band_label: null,
    is_rate_only: false,
    amount: '12000.00',
    ...over,
  };
}

// Issued total: 48,000.00 + 0 + 19,200.00 + 250.00 (the rate-only line adds nothing) = 67,450.00
const LINES: Line[] = [
  line('line-1', '1', { description: 'One-piece WC', unit_price: '400.00', amount: '48000.00' }),
  line('line-2', '2', {
    description: 'Flexible connector',
    unit_price: '0.00',
    amount: '0.00',
  }),
  line('line-3', '14', { description: 'Countertop basin', unit_price: '160.00', amount: '19200.00' }),
  line('line-4', '40', {
    description: 'Shower head',
    quantity: '10',
    unit_price: '25.00',
    amount: '250.00',
  }),
  line('line-5', '41', {
    description: 'Alternate mixer',
    quantity: '1',
    unit_price: '420.00',
    is_rate_only: true,
    amount: null,
  }),
];

function page(overrides: Record<string, unknown> = {}): QuotationSignPage {
  return {
    our_ref: 'PRJQ-0000-R1',
    issue_no: 1,
    sender_logo_url: null,
    signatory_phone: null,
    doc_date: '2026-02-26',
    subject_title: 'FAKE PROJECT P1',
    sender_name: 'Sorento Sdn Bhd',
    recipient_name: 'Customer A',
    recipient_address: 'Level 1, Fake Tower',
    attn_name: 'Buyer A',
    cover_letter: null,
    terms: null,
    signatory_name: 'Ahmad Faizal',
    scopes: [{ scope_label: 'Sanitary ware', scope_total: '67450.00', lines: LINES }],
    grand_total: '67450.00',
    sorento_signature: {
      id: 's1',
      signer_name: 'Ahmad Faizal',
      mode: 'draw',
      image_data_uri: 'data:image/png;base64,SORENTO',
      signed_at: '2026-08-04T02:15:00',
      ip_address: '203.0.113.9',
      gps_lat: null,
      gps_lng: null,
    },
    customer_signature: null,
    accepted_at: null,
    is_accepted: false,
    changes_requested_at: null,
    changes_requested_note: null,
    changes_requested_by_name: null,
    is_changes_requested: false,
    amendment_request: null,
    superseded_by_ref: null,
    can_sign: true,
    sign_blocked_reason: null,
    ...overrides,
  } as unknown as QuotationSignPage;
}

function rowOf(lineId: string, field: string, to: string | null, decision = 'pending', reason: string | null = null) {
  return {
    id: `r-${lineId}-${field}`,
    line_id: lineId,
    field,
    value_from: null,
    value_to: to,
    decision,
    decision_reason: reason,
  };
}

function request(status: 'open' | 'applied', rows: ReturnType<typeof rowOf>[]) {
  return {
    id: 'req-1',
    status,
    submitted_at: '2026-10-30T06:05:00',
    requester_name: 'Buyer A',
    note: null,
    rows,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationSignClient token="tok-123" />
    </QueryClientProvider>,
  );
}

async function open(overrides: Record<string, unknown> = {}) {
  getQuotationSignPage.mockResolvedValue(page(overrides));
  renderPage();
  return screen.findByRole('button', { name: 'Sign and accept' }).catch(() => null);
}

async function suggesting(overrides: Record<string, unknown> = {}) {
  await open(overrides);
  fireEvent.click(await screen.findByRole('button', { name: 'Suggest changes' }));
}

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

/** The table row whose Item cell reads `item`. */
function tr(item: string): HTMLElement {
  const found = Array.from(document.querySelectorAll('tbody tr')).find(
    (row) => row.querySelector('td')?.textContent?.trim() === item,
  );
  if (!found) throw new Error(`no row for item ${item}`);
  return found as HTMLElement;
}

function isOff(button: HTMLElement): boolean {
  return (
    (button as HTMLButtonElement).disabled === true ||
    button.getAttribute('aria-disabled') === 'true'
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  submitAmendmentRequest.mockResolvedValue(
    page({
      amendment_request: request('open', [rowOf('line-1', 'quantity', '110.00')]),
      can_sign: false,
      sign_blocked_reason: 'amendment_open',
    }),
  );
});

// ------------------------------------------------------------------ 1

describe('the entry point and the edit mode', () => {
  it('replaces "Request changes" with ONE "Suggest changes" button', async () => {
    await open();
    expect(await screen.findAllByRole('button', { name: 'Suggest changes' })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Request changes' })).toBeNull();
  });

  it('turns Qty and Unit rate into labelled inputs, keeping the nine headers plus one icon column', async () => {
    await open();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest changes' }));

    for (const item of ['1', '2', '14', '40', '41']) {
      expect(screen.getByLabelText(`Quantity on line ${item}`)).toBeInTheDocument();
    }
    expect(screen.getByLabelText('Unit rate on line 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Unit rate on line 14')).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 1')).toHaveValue(
      screen.getByLabelText('Quantity on line 1').getAttribute('type') === 'number' ? 120 : '120',
    );

    const headers = Array.from(document.querySelectorAll('thead th')).map(
      (th) => th.textContent?.trim() ?? '',
    );
    expect(headers.slice(0, 9)).toEqual([
      'Item',
      'Technical spec',
      'Description',
      'Brand',
      'Product code',
      'Qty',
      'Unit rate',
      'Complete set',
      'Amount',
    ]);
    expect(headers).toHaveLength(10);
  });

  // ---------------------------------------------------------------- 2

  it('gives a zero-priced line no unit rate input, and keeps one on a rate-only line', async () => {
    await suggesting();
    expect(screen.queryByLabelText('Unit rate on line 2')).toBeNull();
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    // Rate-only is quoted at a rate: its price is editable.
    expect(screen.getByLabelText('Unit rate on line 41')).toBeInTheDocument();
  });

  // ---------------------------------------------------------------- 3

  it('stages a removal: strikes the row through, disables its inputs, and Restore undoes it', async () => {
    await suggesting();
    const struck = () => {
      const row = tr('40');
      return (
        row.className.includes('line-through') ||
        row.querySelector('.line-through, s, del, strike') !== null
      );
    };
    expect(struck()).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Remove line 40' }));

    expect(struck()).toBe(true);
    expect(screen.getByLabelText('Quantity on line 40')).toBeDisabled();
    expect(screen.getByLabelText('Unit rate on line 40')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Remove line 40' })).toBeNull();
    // Other rows are not affected.
    expect(screen.getByLabelText('Quantity on line 14')).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Restore line 40' }));

    expect(struck()).toBe(false);
    expect(screen.getByLabelText('Quantity on line 40')).not.toBeDisabled();
    expect(screen.getByLabelText('Unit rate on line 40')).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Remove line 40' })).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ 4

describe('a quantity below 1 cannot be sent', () => {
  it.each([['0'], [''], ['abc'], ['-2'], ['0.5']])(
    'blocks Send with a visible message for %j and calls nothing',
    async (bad) => {
      await suggesting();
      // A valid change elsewhere, so the quantity is the ONLY thing standing in the way.
      type('Unit rate on line 14', '150.00');
      type('Quantity on line 1', bad);

      expect(screen.getByText(/at least 1/i)).toBeVisible();
      const send = screen.getByRole('button', { name: 'Send suggestions' });
      fireEvent.click(send);
      await act(async () => {});
      expect(submitAmendmentRequest).not.toHaveBeenCalled();
      expect(isOff(send)).toBe(true);

      type('Quantity on line 1', '5');
      expect(screen.queryByText(/at least 1/i)).toBeNull();
      expect(isOff(screen.getByRole('button', { name: 'Send suggestions' }))).toBe(false);
    },
  );
});

// ------------------------------------------------------------------ 5 and 6

describe('the summary and Send', () => {
  async function theWorkedExample() {
    await suggesting();
    type('Quantity on line 1', '110');
    type('Unit rate on line 1', '380.00');
    type('Unit rate on line 14', '150.00');
    // Typed back to the issued value: not a change.
    type('Quantity on line 2', '120.00');
    // Edited, then staged for removal: only the removal counts.
    type('Quantity on line 40', '5');
    fireEvent.click(screen.getByRole('button', { name: 'Remove line 40' }));
    fireEvent.change(screen.getByLabelText('Anything else (optional)'), {
      target: { value: 'Please deliver the WCs in two batches.' },
    });
  }

  it('shows the number of changed lines and the total before and after, on "Send suggestions"', async () => {
    await theWorkedExample();
    const text = document.body.textContent ?? '';
    expect(text).toMatch(/3 lines/);
    // 41,800.00 (110 x 380) + 0 + 18,000.00 (120 x 150) = 59,800.00; the removed line drops out.
    expect(text).toMatch(/67,450\.00\s*(→|->)\s*(RM\s*)?59,800\.00/);
    expect(screen.getByRole('button', { name: 'Send suggestions' })).toBeInTheDocument();
  });

  it('sends ONLY the changed lines and fields, a removal as remove:true, plus the note', async () => {
    await theWorkedExample();
    fireEvent.click(screen.getByRole('button', { name: 'Send suggestions' }));
    await waitFor(() => expect(submitAmendmentRequest).toHaveBeenCalledTimes(1));

    const [token, body] = submitAmendmentRequest.mock.calls[0];
    expect(token).toBe('tok-123');
    expect(body.requester_name).toBe('Buyer A');
    expect(body.note).toBe('Please deliver the WCs in two batches.');
    expect(body.lines).toHaveLength(3);
    expect(requestQuotationChanges).not.toHaveBeenCalled();

    const by = (id: string) => body.lines.find((l: { line_id: string }) => l.line_id === id);
    const wc = by('line-1');
    expect(Number(wc.quantity)).toBe(110);
    expect(Number(wc.unit_price)).toBe(380);
    expect(wc.remove).toBe(false);

    const basin = by('line-3');
    expect(basin.quantity).toBeNull();
    expect(Number(basin.unit_price)).toBe(150);
    expect(basin.remove).toBe(false);

    expect(by('line-4')).toEqual({
      line_id: 'line-4',
      quantity: null,
      unit_price: null,
      remove: true,
    });
    // Untouched, and typed-back-to-issued, lines are not in the request.
    expect(by('line-2')).toBeUndefined();
    expect(by('line-5')).toBeUndefined();
  });

  it('sends a null note when the box is empty', async () => {
    await suggesting();
    type('Unit rate on line 14', '150.00');
    fireEvent.click(screen.getByRole('button', { name: 'Send suggestions' }));
    await waitFor(() => expect(submitAmendmentRequest).toHaveBeenCalledTimes(1));
    expect(submitAmendmentRequest.mock.calls[0][1].note ?? null).toBeNull();
  });
});

// ------------------------------------------------------------------ 7 and 8

describe('why Sign is off, said once', () => {
  const withTerms = { terms: '<p>CLAUSE A</p>' };

  it('an open request disables Sign, says so, and hides the terms tick and its reason', async () => {
    await open({
      ...withTerms,
      can_sign: false,
      sign_blocked_reason: 'amendment_open',
      amendment_request: request('open', [
        rowOf('line-1', 'quantity', '110.00'),
        rowOf('line-3', 'unit_price', '150.00'),
      ]),
    });

    const sign = await screen.findByRole('button', { name: 'Sign and accept' });
    expect(isOff(sign)).toBe(true);
    expect(screen.getByText(OPEN_SENTENCE)).toBeInTheDocument();
    expect(screen.queryByText(TICK_HINT)).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('with no open request and the terms unticked, only the terms reason shows', async () => {
    await open(withTerms);
    expect(await screen.findByRole('checkbox')).not.toBeChecked();
    fireEvent.change(await screen.findByRole('textbox', { name: 'Your name' }), {
      target: { value: 'CONTACT B' },
    });

    expect(screen.getByText(TICK_HINT)).toBeInTheDocument();
    expect(screen.queryByText(OPEN_SENTENCE)).toBeNull();
  });
});

// ------------------------------------------------------------------ 9

describe('an answered request shows its answers in the cells', () => {
  it('shows Accepted, Not accepted with the reason, and an accepted removal; Sign is off', async () => {
    await open({
      can_sign: false,
      sign_blocked_reason: 'amendment_applied',
      amendment_request: request('applied', [
        rowOf('line-1', 'quantity', '110.00', 'accepted'),
        rowOf('line-1', 'unit_price', '380.00', 'accepted'),
        rowOf('line-3', 'unit_price', '150.00', 'rejected', 'Already at the project price.'),
        rowOf('line-4', 'remove', null, 'accepted'),
      ]),
    });
    await screen.findByText('Sanitary ware');

    const wc = tr('1');
    expect(within(wc).getAllByText('Accepted')).toHaveLength(2);
    expect(wc.textContent).toMatch(/110/);
    expect(wc.textContent).toMatch(/RM\s*380\.00/);

    const basin = tr('14');
    expect(within(basin).getByText('Not accepted')).toBeInTheDocument();
    expect(within(basin).getByText(/Already at the project price\./)).toBeInTheDocument();
    expect(basin.textContent).toMatch(/RM\s*160\.00/);

    expect(tr('40').textContent).toMatch(/Removal accepted/);

    // Untouched lines carry no answer.
    expect(within(tr('2')).queryByText(/Accepted|Not accepted/)).toBeNull();

    // The issue can no longer be signed.
    expect(screen.queryByRole('button', { name: 'Suggest changes' })).toBeNull();
    const sign = screen.queryByRole('button', { name: 'Sign and accept' });
    if (sign) expect(isOff(sign)).toBe(true);
  });
});

// ------------------------------------------------------------------ 10

describe('a replaced revision', () => {
  it('says which quotation replaced it and offers neither suggesting nor signing', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({
        superseded_by_ref: 'Quotation No. PRJQ-0000-R2',
        can_sign: false,
        sign_blocked_reason: 'superseded',
      }),
    );
    renderPage();

    expect(await screen.findByText(REPLACED)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Suggest changes' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Sign and accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Request changes' })).toBeNull();
  });
});
