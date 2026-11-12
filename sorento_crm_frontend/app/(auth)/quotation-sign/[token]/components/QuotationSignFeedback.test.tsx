/**
 * PS-QUOTE-MATRIX, customer side (R18, R19, mock v3 frame 4): a scope with column headers reads
 * as a read-only grid, and the customer leaves feedback on a whole item or on one cell, with an
 * optional hint. Nothing is accepted, rejected or applied. Values invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationSignLine, QuotationSignPage } from '../../services/quotationSignService';
import {
  EMPTY_FEEDBACK,
  feedbackBody,
  feedbackError,
  feedbackItem,
  hintsFor,
  type FeedbackTarget,
} from './quotationSuggest';

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = vi.fn(
    () => null,
  ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});

const getQuotationSignPage = vi.fn();
const submitQuotationFeedback = vi.fn();

vi.mock('../../services/quotationSignService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/quotationSignService')>();
  return {
    ...actual,
    getQuotationSignPage: (...args: unknown[]) => getQuotationSignPage(...args),
    submitQuotationFeedback: (...args: unknown[]) => submitQuotationFeedback(...args),
  };
});

// The page's open beacon reaches NextAuth's logger outside a browser; not what this file tests.
vi.mock('../../hooks/useQuotationViewBeacon', () => ({ useQuotationViewBeacon: () => {} }));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { QuotationSignClient } from './QuotationSignClient';
import { SIGN_COLUMNS } from './signColumns.fixture';

function signLine(overrides: Partial<QuotationSignLine> = {}): QuotationSignLine {
  return {
    id: 'line-1',
    item_label: '1',
    description: 'Water closet',
    technical_spec: null,
    brand: 'SORENTO',
    product_code: 'SRT-WC-01',
    quantity: '120',
    unit_price: '850.00',
    complete_set: null,
    band_label: null,
    is_rate_only: false,
    amount: '102000.00',
    ...overrides,
  };
}

// Since #2106 the server sends the PRINTED item number as item_label.
const SINK = signLine({
  id: 'line-sink',
  item_label: '1',
  description: 'KS903 kitchen sink',
  product_code: 'KS903',
  brand: 'Cabana',
  quantity: '503',
  unit_price: '310.00',
  amount: '155930.00',
  qty_cells: { 'a-kit': '120.00', 'b-kit': '250.00', 'c-kit': '133.00' },
});

function page(overrides: Partial<QuotationSignPage> = {}): QuotationSignPage {
  return {
    our_ref: 'Q-2611-0007',
    issue_no: 1,
    amendment_request: null,
    superseded_by_ref: null,
    can_sign: true,
    sign_blocked_reason: null,
    sender_logo_url: null,
    signatory_phone: null,
    doc_date: '2026-11-02',
    subject_title: 'PROPOSED SANITARY WARES',
    sender_name: 'Sorento Sdn Bhd',
    recipient_name: 'Developer Sdn Bhd',
    recipient_address: null,
    attn_name: 'Kelly',
    cover_letter: null,
    terms: null,
    signatory_name: 'Sales A',
    scopes: [
      {
        scope_label: 'UNIT',
        scope_total: '155930.00',
        columns: SIGN_COLUMNS,
        matrix_columns: [
          { key: 'a', label: 'Type A - 1 BH', cols: [{ key: 'a-bh', label: '1 BH' }, { key: 'a-kit', label: 'Kitchen' }] },
          { key: 'b', label: 'Type B - 2 BH', cols: [{ key: 'b-bh', label: '2 BH' }, { key: 'b-kit', label: 'Kitchen' }] },
          { key: 'c', label: 'Type C - 3 BH', cols: [{ key: 'c-bh', label: '3 BH' }, { key: 'c-kit', label: 'Kitchen' }] },
          { key: 'bt', label: 'Break tank', cols: [] },
        ],
        lines: [SINK],
      },
      {
        scope_label: 'GUARD HOUSE',
        scope_total: '102000.00',
        columns: SIGN_COLUMNS,
        lines: [signLine()],
      },
    ],
    grand_total: '257930.00',
    sorento_signature: null,
    customer_signature: null,
    accepted_at: null,
    is_accepted: false,
    changes_requested_at: null,
    changes_requested_note: null,
    changes_requested_by_name: null,
    is_changes_requested: false,
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuotationSignClient token="tok-1" />
    </QueryClientProvider>,
  );
}

async function openScope(label: string) {
  fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^${label}`) }));
}

beforeEach(() => {
  vi.clearAllMocks();
  getQuotationSignPage.mockResolvedValue(page());
  submitQuotationFeedback.mockImplementation(async () => page());
});

describe('feedback rules (quotationSuggest)', () => {
  const item: FeedbackTarget = { line: SINK, itemLabel: 'KS903', scopeLabel: 'UNIT' };
  const cell: FeedbackTarget = { ...item, cell: { key: 'c-kit', label: 'Type C - 3 BH / Kitchen', value: '133' } };

  it('offers a cell a quantity only, an item every hint', () => {
    expect(hintsFor(cell)).toEqual(['none', 'quantity']);
    expect(hintsFor(item)).toEqual(['none', 'quantity', 'unit_price', 'remove', 'model_swap']);
  });

  it('needs a note without a hint, and a valid value with one', () => {
    expect(feedbackError(item, EMPTY_FEEDBACK)).toBe('Write a note.');
    expect(feedbackError(item, { ...EMPTY_FEEDBACK, note: 'Hi' })).toBeNull();
    expect(feedbackError(item, { ...EMPTY_FEEDBACK, hint: 'quantity', value: '0' })).toBeNull();
    expect(feedbackError(item, { ...EMPTY_FEEDBACK, hint: 'quantity', value: '-1' })).not.toBeNull();
    expect(feedbackError(item, { ...EMPTY_FEEDBACK, hint: 'unit_price', value: '0' })).toBe('Price must be above 0.');
    expect(feedbackError(item, { ...EMPTY_FEEDBACK, hint: 'remove' })).toBeNull();
    expect(feedbackError(item, { ...EMPTY_FEEDBACK, hint: 'model_swap' })).toBe('Name the other model.');
    expect(feedbackError(item, { ...EMPTY_FEEDBACK, hint: 'model_swap', model: 'UR-200' })).toBeNull();
    expect(feedbackError(cell, { ...EMPTY_FEEDBACK, hint: 'unit_price', value: '5' })).not.toBeNull();
  });

  it('builds one item per note in the contract\'s shape', () => {
    expect(feedbackItem(cell, { ...EMPTY_FEEDBACK, note: ' needs 140 ', hint: 'quantity', value: '140' })).toEqual({
      line_id: 'line-sink',
      cell_key: 'c-kit',
      kind: 'quantity',
      value: '140',
      note: 'needs 140',
    });
    expect(feedbackItem(item, { ...EMPTY_FEEDBACK, hint: 'model_swap', model: 'UR-200', value: '' })).toEqual({
      line_id: 'line-sink',
      kind: 'model_swap',
      model: 'UR-200',
    });
    expect(feedbackItem(item, { ...EMPTY_FEEDBACK, note: 'Hi' })).toEqual({ line_id: 'line-sink', kind: 'note', note: 'Hi' });
    expect(feedbackBody([], '  ', '')).toEqual({ items: [], note: null, requester_name: null });
  });
});

describe('the sign page grid and feedback (PS-QUOTE-MATRIX)', () => {
  it('opens a scope with columns as a read-only grid: headers over columns, the item first', async () => {
    renderPage();
    await openScope('UNIT');

    const table = screen.getAllByTestId('quotation-sign-scroller')[0];
    expect(within(table).getByText('Type C - 3 BH')).toBeInTheDocument();
    expect(within(table).getByText('Break tank')).toBeInTheDocument();
    expect(within(table).getAllByText('Kitchen')).toHaveLength(3);
    expect(within(table).getByText('Total qty')).toBeInTheDocument();
    expect(within(table).getByRole('button', { name: 'Leave feedback on KS903 kitchen sink, Type C - 3 BH / Kitchen' })).toHaveTextContent('133');
    // Read-only: no inputs at all.
    expect(within(table).queryByRole('textbox')).toBeNull();
  });

  it('sends a cell note with a suggested quantity', async () => {
    renderPage();
    await openScope('UNIT');
    fireEvent.click(screen.getByRole('button', { name: 'Leave feedback on KS903 kitchen sink, Type C - 3 BH / Kitchen' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByTestId('feedback-where')).toHaveTextContent(
      'KS903 kitchen sink · Type C - 3 BH / Kitchen (now 133)',
    );
    fireEvent.change(within(dialog).getByLabelText('Your note'), { target: { value: 'Type C needs 140.' } });
    fireEvent.change(within(dialog).getByLabelText('Suggested quantity (optional)'), { target: { value: '140' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send feedback' }));

    await waitFor(() =>
      expect(submitQuotationFeedback).toHaveBeenCalledWith('tok-1', {
        items: [{ line_id: 'line-sink', cell_key: 'c-kit', kind: 'quantity', value: '140', note: 'Type C needs 140.' }],
        note: null,
        requester_name: 'Kelly',
      }),
    );
  });

  it('sends an item note with a price hint on a scope without columns', async () => {
    renderPage();
    await openScope('GUARD HOUSE');
    fireEvent.click(screen.getByRole('button', { name: 'Leave feedback on Water closet' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByLabelText('Price'));
    fireEvent.change(within(dialog).getByLabelText(/Suggested price/), { target: { value: '780' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send feedback' }));

    await waitFor(() =>
      expect(submitQuotationFeedback).toHaveBeenCalledWith('tok-1', {
        items: [{ line_id: 'line-1', kind: 'unit_price', value: '780' }],
        note: null,
        requester_name: 'Kelly',
      }),
    );
  });

  it('refuses an empty note and says why', async () => {
    renderPage();
    await openScope('GUARD HOUSE');
    fireEvent.click(screen.getByRole('button', { name: 'Leave feedback on Water closet' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send feedback' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Write a note.');
    expect(submitQuotationFeedback).not.toHaveBeenCalled();
  });

  it('sends a free note on the whole quotation', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Leave a note' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Your note'), { target: { value: 'Call me.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send feedback' }));
    await waitFor(() =>
      expect(submitQuotationFeedback).toHaveBeenCalledWith('tok-1', {
        items: [],
        note: 'Call me.',
        requester_name: 'Kelly',
      }),
    );
  });

  it('marks what already has feedback, and never blocks signing', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({
        amendment_request: {
          id: 'r1',
          submitted_at: '2026-11-02T10:40:00',
          rows: [
            { id: 'f1', line_id: 'line-sink', cell_key: 'c-kit' },
            { id: 'f2', line_id: 'line-sink', cell_key: null },
          ],
        },
      }),
    );
    renderPage();
    await openScope('UNIT');
    expect(screen.getByTestId('sign-feedback-corner')).toBeInTheDocument();
    expect(screen.getByTestId('sign-feedback-dot')).toBeInTheDocument();
    // The sign block is the ordinary one, and nothing reads as accepted or rejected.
    expect(screen.getByText('Signing below accepts this quotation.')).toBeInTheDocument();
    expect(screen.queryByText(/not accepted|Answered|with Sorento/i)).toBeNull();
    expect(screen.getByRole('button', { name: 'Leave a note' })).toBeInTheDocument();
  });

  it('offers no feedback once the quotation is accepted', async () => {
    getQuotationSignPage.mockResolvedValue(page({ is_accepted: true, sign_blocked_reason: 'accepted' }));
    renderPage();
    await openScope('UNIT');
    expect(screen.queryByRole('button', { name: 'Leave a note' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Leave feedback on/ })).toBeNull();
  });
});

describe('lines named by description, not the printed number (fix round 2, B2)', () => {
  it('names the grid row and the feedback dialog by description; the plain ITEM cell keeps "1"', async () => {
    renderPage();
    await openScope('UNIT');
    const grid = screen.getAllByTestId('quotation-sign-scroller')[0];
    const row = within(grid).getByText('KS903 kitchen sink').closest('tr') as HTMLElement;
    // Brand and code as a muted second line, as mock v3 frame 4.
    expect(within(row).getByText('Cabana · KS903')).toBeInTheDocument();

    fireEvent.click(within(row).getByRole('button', { name: 'Leave feedback on KS903 kitchen sink' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'KS903 kitchen sink' })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await openScope('GUARD HOUSE');
    const plain = screen.getAllByTestId('quotation-sign-scroller')[1];
    const first = within(plain).getAllByRole('row')[1];
    expect(within(first).getAllByRole('cell')[0]).toHaveTextContent(/^1$/);
    expect(within(first).getByRole('button', { name: 'Leave feedback on Water closet' })).toBeInTheDocument();
  });
});
