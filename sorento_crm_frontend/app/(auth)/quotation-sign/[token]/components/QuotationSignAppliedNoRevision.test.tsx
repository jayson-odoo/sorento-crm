/**
 * QUOTE-CUSTOMER-AMEND fix round 3 (S4 page shape): a request applied WITHOUT a revision (a note,
 * or every row rejected) blocks nothing. The page carries it with `sign_blocked_reason: null`, so
 * the pad is live, Suggest changes is offered again, and the answers stay in their cells.
 * Values invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { QuotationSignPage } from '../../services/quotationSignService';

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = vi.fn(
    () => null,
  ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});

const getQuotationSignPage = vi.fn();
vi.mock('../../services/quotationSignService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/quotationSignService')>();
  return { ...actual, getQuotationSignPage: (...args: unknown[]) => getQuotationSignPage(...args) };
});

import { QuotationSignClient } from './QuotationSignClient';

const PAGE = {
  our_ref: 'PRJQ-0000-R1',
  issue_no: 1,
  doc_date: '2026-02-26',
  subject_title: 'FAKE PROJECT P1',
  sender_name: 'Sorento Sdn Bhd',
  sender_logo_url: null,
  recipient_name: 'Customer A',
  recipient_address: null,
  attn_name: 'Buyer A',
  cover_letter: null,
  terms: null,
  signatory_name: 'Ahmad Faizal',
  signatory_phone: null,
  scopes: [
    {
      scope_label: 'Sanitary ware',
      scope_total: '19200.00',
      lines: [
        {
          id: 'line-1',
          item_label: '1',
          description: 'Countertop basin',
          technical_spec: null,
          brand: null,
          product_code: 'ZZT-BSN',
          quantity: '120',
          unit_price: '160.00',
          complete_set: null,
          band_label: null,
          is_rate_only: false,
          amount: '19200.00',
        },
      ],
    },
  ],
  grand_total: '19200.00',
  sorento_signature: null,
  customer_signature: null,
  accepted_at: null,
  is_accepted: false,
  changes_requested_at: null,
  changes_requested_note: null,
  changes_requested_by_name: null,
  is_changes_requested: false,
  amendment_request: {
    id: 'req-1',
    status: 'applied',
    submitted_at: '2026-10-30T06:05:00',
    requester_name: 'Buyer A',
    note: null,
    rows: [
      {
        id: 'r1',
        line_id: 'line-1',
        field: 'unit_price',
        value_from: '160.00',
        value_to: '150.00',
        decision: 'rejected',
        decision_reason: 'Already at the project price.',
      },
    ],
  },
  superseded_by_ref: null,
  can_sign: true,
  sign_blocked_reason: null,
} as unknown as QuotationSignPage;

describe('a request applied without a revision', () => {
  it('leaves the pad live and offers Suggest changes again, with the answer in its cell', async () => {
    getQuotationSignPage.mockResolvedValue(PAGE);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <QuotationSignClient token="tok-1" />
      </QueryClientProvider>,
    );

    const sign = await screen.findByRole('button', { name: 'Sign and accept' });
    expect(screen.getByRole('button', { name: 'Suggest changes' })).toBeInTheDocument();
    expect(screen.queryByText('You can sign once Sorento has answered your suggestions.')).toBeNull();
    expect(screen.queryByText(/Sorento answered/)).toBeNull();
    expect(screen.getByText('Not accepted')).toBeInTheDocument();

    // With a name in, the only step left is the ink: Sign waits on the signature (aria-disabled
    // until drawn, as on any page), never on the request.
    fireEvent.change(screen.getByRole('textbox', { name: 'Your name' }), {
      target: { value: 'Buyer A' },
    });
    expect(sign).toBeInTheDocument();
    expect(screen.getByText('Draw your signature to accept.')).toBeInTheDocument();
    expect(screen.getByTestId('signature-pad-canvas')).toBeInTheDocument();
  });
});
