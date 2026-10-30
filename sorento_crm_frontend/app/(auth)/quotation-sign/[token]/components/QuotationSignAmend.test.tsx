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

// ------------------------------------------------------------------ placement (owner round 1)

describe('where "Suggest changes" lives', () => {
  it('is ONE button in the header of the Quotation card, and not in the Accepted by card', async () => {
    await open();
    const buttons = await screen.findAllByRole('button', { name: 'Suggest changes' });
    expect(buttons).toHaveLength(1);
    const button = buttons[0];

    // The Quotation card: the nearest ancestor of its title that also holds the sections.
    const title = screen.getByRole('heading', { name: 'Quotation' });
    const header = title.parentElement as HTMLElement;
    expect(header).toContainElement(button);

    let quotationCard: HTMLElement | null = title.parentElement;
    while (quotationCard && !within(quotationCard).queryByText(/Sanitary ware/)) {
      quotationCard = quotationCard.parentElement;
    }
    expect(quotationCard).not.toBeNull();
    expect(quotationCard).toContainElement(button);

    // The sign card holds the name box; the button is neither in it nor in its row.
    const signTitle = screen.getByRole('heading', { name: 'Accepted by' });
    let signCard: HTMLElement | null = signTitle.parentElement;
    while (signCard && !within(signCard).queryByLabelText('Your name')) {
      signCard = signCard.parentElement;
    }
    expect(signCard).not.toBeNull();
    expect(signCard).not.toContainElement(button);
    expect(screen.queryByText('Not ready to sign this?')).toBeNull();
  });
});

// ------------------------------------------------------------------ the bar

describe('the suggestion bar', () => {
  it('holds only Discard and Send suggestions: no count and no before/after total', async () => {
    await suggesting();
    type('Quantity on line 1', '110');
    type('Unit rate on line 14', '150.00');

    const send = screen.getByRole('button', { name: 'Send suggestions' });
    const discard = screen.getByRole('button', { name: 'Discard' });
    expect(send).toBeInTheDocument();
    expect(discard).toBeInTheDocument();

    expect(screen.queryByText(/Your suggestions/)).toBeNull();
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/\d+ lines?\s*Total/);
    expect(text).not.toMatch(/RM\s*[\d,]+\.\d\d\s*(→|->)\s*RM\s*[\d,]+\.\d\d/);

    // The bar is one row holding exactly those two controls.
    const bar = send.parentElement as HTMLElement;
    expect(bar).toContainElement(discard);
    expect(within(bar).getAllByRole('button')).toHaveLength(2);
    // Discard first, Send at the right end.
    expect(
      discard.compareDocumentPosition(send) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

// ------------------------------------------------------------------ every money figure shows its change

describe('every money figure shows the change, with "quoted X" beneath', () => {
  const QUOTED = /quoted/i;

  /** One section, two lines: 3 x 360.00 = 1,080.00 and 2 x 100.00 = 200.00. Total 1,280.00. */
  function smallPage(): QuotationSignPage {
    return page({
      scopes: [
        {
          scope_label: 'Sanitary ware',
          scope_total: '1280.00',
          lines: [
            line('m-1', '1', {
              description: 'Fake WC',
              quantity: '3',
              unit_price: '360.00',
              amount: '1080.00',
            }),
            line('m-2', '2', {
              description: 'Fake basin',
              quantity: '2',
              unit_price: '100.00',
              amount: '200.00',
            }),
          ],
        },
      ],
      grand_total: '1280.00',
    });
  }

  async function small() {
    getQuotationSignPage.mockResolvedValue(smallPage());
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest changes' }));
    await screen.findByLabelText('Quantity on line 1');
  }

  const amountCell = (item: string) => {
    const cells = tr(item).querySelectorAll('td');
    // Amount is the last data cell before the icon column.
    return cells[cells.length - 2] as HTMLElement;
  };
  const sectionHeader = () =>
    screen.getByRole('button', { name: /Sanitary ware/ }) as HTMLElement;
  const grandTotalRow = () =>
    screen.getByText(/total amount/i).parentElement as HTMLElement;

  it('shows no "quoted" anywhere before anything is changed', async () => {
    await small();
    expect(amountCell('1').textContent).not.toMatch(QUOTED);
    expect(sectionHeader().textContent).not.toMatch(QUOTED);
    expect(grandTotalRow().textContent).not.toMatch(QUOTED);
  });

  it('a quantity change moves the line Amount, the section subtotal and the grand total', async () => {
    await small();
    type('Quantity on line 1', '6');

    // 6 x 360.00 = 2,160.00 (was 1,080.00)
    expect(amountCell('1').textContent).toMatch(/RM\s*2,160\.00/);
    expect(amountCell('1').textContent).toMatch(/quoted\s*RM\s*1,080\.00/);
    // 2,160.00 + 200.00 = 2,360.00 (was 1,280.00)
    expect(sectionHeader().textContent).toMatch(/RM\s*2,360\.00/);
    expect(sectionHeader().textContent).toMatch(/quoted\s*RM\s*1,280\.00/);
    expect(grandTotalRow().textContent).toMatch(/RM\s*2,360\.00/);
    expect(grandTotalRow().textContent).toMatch(/quoted\s*RM\s*1,280\.00/);

    // The line nobody touched shows no "quoted".
    expect(amountCell('2').textContent).not.toMatch(QUOTED);
    expect(amountCell('2').textContent).toMatch(/RM\s*200\.00/);
  });

  it('a price change works the same way', async () => {
    await small();
    type('Unit rate on line 2', '150.00');

    // 2 x 150.00 = 300.00 (was 200.00); section and total 1,380.00 (was 1,280.00)
    expect(amountCell('2').textContent).toMatch(/RM\s*300\.00/);
    expect(amountCell('2').textContent).toMatch(/quoted\s*RM\s*200\.00/);
    expect(sectionHeader().textContent).toMatch(/RM\s*1,380\.00/);
    expect(sectionHeader().textContent).toMatch(/quoted\s*RM\s*1,280\.00/);
    expect(grandTotalRow().textContent).toMatch(/RM\s*1,380\.00/);
    expect(grandTotalRow().textContent).toMatch(/quoted\s*RM\s*1,280\.00/);
    expect(amountCell('1').textContent).not.toMatch(QUOTED);
  });

  it('a removed line drops out of the subtotal and total, and keeps its own struck-through row', async () => {
    await small();
    fireEvent.click(screen.getByRole('button', { name: 'Remove line 2' }));

    // 1,280.00 - 200.00 = 1,080.00
    expect(sectionHeader().textContent).toMatch(/RM\s*1,080\.00/);
    expect(sectionHeader().textContent).toMatch(/quoted\s*RM\s*1,280\.00/);
    expect(grandTotalRow().textContent).toMatch(/RM\s*1,080\.00/);
    expect(grandTotalRow().textContent).toMatch(/quoted\s*RM\s*1,280\.00/);

    // Its own cell is not given a new value: the row stays, struck through, as quoted.
    const row = tr('2');
    expect(
      row.className.includes('line-through') || row.querySelector('.line-through, s, del') !== null,
    ).toBe(true);
    expect(amountCell('2').textContent).toMatch(/RM\s*200\.00/);
    expect(amountCell('2').textContent).not.toMatch(QUOTED);

    // Restoring puts every figure back, and the "quoted" text goes with it.
    fireEvent.click(screen.getByRole('button', { name: 'Restore line 2' }));
    expect(sectionHeader().textContent).not.toMatch(QUOTED);
    expect(grandTotalRow().textContent).not.toMatch(QUOTED);
  });
});

// ------------------------------------------------------------------ Send, and the confirm step

describe('Send suggestions opens a confirm step that holds the note', () => {
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
  }

  /** The confirm step's own final button is named "Send" (the bar's is "Send suggestions"). */
  async function confirmStep() {
    fireEvent.click(screen.getByRole('button', { name: 'Send suggestions' }));
    const dialog = await screen.findByRole('dialog');
    return {
      dialog,
      note: within(dialog).getByLabelText('Anything else (optional)'),
      send: within(dialog).getByRole('button', { name: 'Send' }),
      cancel: within(dialog).getByRole('button', { name: 'Cancel' }),
    };
  }

  it('has no note box on the page, and nothing is sent, until Send suggestions is clicked', async () => {
    await theWorkedExample();
    expect(screen.queryByLabelText('Anything else (optional)')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Send suggestions' }));
    await screen.findByRole('dialog');
    await act(async () => {});
    expect(submitAmendmentRequest).not.toHaveBeenCalled();
  });

  it('sends ONLY the changed lines and fields, a removal as remove:true, with the note, on the final Send', async () => {
    await theWorkedExample();
    const { note, send } = await confirmStep();
    fireEvent.change(note, { target: { value: 'Please deliver the WCs in two batches.' } });
    fireEvent.click(send);
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

  it('sends a null note when the box is left empty', async () => {
    await suggesting();
    type('Unit rate on line 14', '150.00');
    const { send } = await confirmStep();
    fireEvent.click(send);
    await waitFor(() => expect(submitAmendmentRequest).toHaveBeenCalledTimes(1));
    expect(submitAmendmentRequest.mock.calls[0][1].note ?? null).toBeNull();
  });

  it('Cancel closes the confirm step, keeps the edits and sends nothing', async () => {
    await theWorkedExample();
    const { note, cancel } = await confirmStep();
    fireEvent.change(note, { target: { value: 'Never mind.' } });
    fireEvent.click(cancel);
    await act(async () => {});

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submitAmendmentRequest).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Quantity on line 1')).toHaveValue(
      screen.getByLabelText('Quantity on line 1').getAttribute('type') === 'number' ? 110 : '110',
    );
    expect(screen.getByRole('button', { name: 'Send suggestions' })).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ 7 and 8

describe('why Sign is off, said once', () => {
  const withTerms = { terms: '<p>CLAUSE A</p>' };

  const preparedBy = () => screen.getByRole('heading', { name: /Prepared by/ });
  const noSignBlock = () => {
    expect(screen.queryByLabelText('Your name')).toBeNull();
    expect(screen.queryByRole('textbox', { name: 'Your name' })).toBeNull();
    for (const tab of ['Draw', 'Type', 'Initials']) {
      expect(screen.queryByRole('tab', { name: tab })).toBeNull();
    }
    expect(screen.queryByText('Sign here')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Sign and accept' })).toBeNull();
    expect(screen.queryByText(OPEN_SENTENCE)).toBeNull();
    expect(screen.queryByText(TICK_HINT)).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Accepted by' })).toBeNull();
  };

  it('an open request hides the whole sign block: only the waiting banner stands in its place', async () => {
    await open({
      ...withTerms,
      can_sign: false,
      sign_blocked_reason: 'amendment_open',
      amendment_request: request('open', [
        rowOf('line-1', 'quantity', '110.00'),
        rowOf('line-3', 'unit_price', '150.00'),
      ]),
    });

    expect(await screen.findByText('Your suggestions are with Sorento')).toBeInTheDocument();
    noSignBlock();
    expect(screen.queryByRole('button', { name: 'Suggest changes' })).toBeNull();
    // The Sorento signature card is not part of the sign block.
    expect(preparedBy()).toBeInTheDocument();
  });

  it('control: the same steps with no open request leave Sign enabled', async () => {
    await open({ terms: '<p>CLAUSE A</p>' });
    await screen.findByRole('button', { name: 'Sign and accept' });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Type' }), { button: 0 });

    expect(isOff(screen.getByRole('button', { name: 'Sign and accept' }))).toBe(false);
    expect(screen.queryByText(OPEN_SENTENCE)).toBeNull();
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

describe('the sign block after the request is answered', () => {
  const decided = [
    rowOf('line-1', 'quantity', '110.00', 'rejected', 'Not this time'),
    rowOf('line-3', 'unit_price', '150.00', 'rejected', 'Already at the project price.'),
  ];

  it('answered with NO revision: the name, the pad and Sign and accept come back', async () => {
    await open({
      can_sign: true,
      sign_blocked_reason: null,
      amendment_request: { ...request('applied', decided), revised: false },
    });

    expect(await screen.findByRole('button', { name: 'Sign and accept' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Your name' })).toBeInTheDocument();
    for (const tab of ['Draw', 'Type', 'Initials']) {
      expect(screen.getByRole('tab', { name: tab })).toBeInTheDocument();
    }
    // The waiting banner is gone, and the answers still show in the cells.
    expect(screen.queryByText('Your suggestions are with Sorento')).toBeNull();
    await screen.findByText('Sanitary ware');
    expect(within(tr('14')).getByText('Not accepted')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Prepared by/ })).toBeInTheDocument();
  });

  it('answered WITH a revision: its own answered card, no name, no pad, no Sign', async () => {
    await open({
      can_sign: false,
      sign_blocked_reason: 'amendment_applied',
      amendment_request: {
        ...request('applied', [rowOf('line-1', 'quantity', '110.00', 'accepted')]),
        revised: true,
      },
    });

    expect(await screen.findByText(/Sorento answered/)).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Your name' })).toBeNull();
    for (const tab of ['Draw', 'Type', 'Initials']) {
      expect(screen.queryByRole('tab', { name: tab })).toBeNull();
    }
    expect(screen.queryByRole('button', { name: 'Sign and accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Suggest changes' })).toBeNull();
    expect(screen.getByRole('heading', { name: /Prepared by/ })).toBeInTheDocument();
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
