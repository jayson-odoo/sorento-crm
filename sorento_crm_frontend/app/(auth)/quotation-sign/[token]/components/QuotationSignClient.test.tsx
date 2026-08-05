/**
 * S7 - the customer's counter-sign page.
 *
 * Three things here are the difference between a signature that means something and a support
 * call: a rate-only line must print the WORDS (RM 0.00 tells the customer it is free), an already
 * accepted quotation must offer no way to sign it again, and a dead link must read as a plain fact
 * rather than as a fault the reader caused.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationSignPage } from '../../services/quotationSignService';

/**
 * jsdom ships no 2d context and logs "Not implemented" for every attempt. The pad already treats
 * a null context as "nothing to paint", so returning null keeps its behaviour identical and stops
 * the noise. Rasterising is a browser concern, checked in Playwright, and nothing here draws.
 */
beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = vi.fn(
    () => null,
  ) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});

const getQuotationSignPage = vi.fn();

vi.mock('../../services/quotationSignService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/quotationSignService')>();
  return {
    ...actual,
    getQuotationSignPage: (...args: unknown[]) => getQuotationSignPage(...args),
  };
});

import { QuotationSignClient } from './QuotationSignClient';
import { QuotationSignError } from '../../services/quotationSignService';

function page(overrides: Partial<QuotationSignPage> = {}): QuotationSignPage {
  return {
    our_ref: 'SRT/Q/2026/0141 (R2)',
    issue_no: 2,
    doc_date: '2026-02-26',
    subject_title: 'CADANGAN MEMBINA PANGSAPURI RUMAH IDAM',
    sender_name: 'Sorento Sdn Bhd',
    recipient_name: 'Nadi Cergas Sdn Bhd',
    recipient_address: 'Level 8, Menara Test\nKuala Lumpur',
    attn_name: 'Kelly',
    cover_letter: null,
    terms: null,
    signatory_name: 'Ahmad Faizal',
    scopes: [
      {
        scope_label: 'Townhouse',
        scope_total: '235000.00',
        lines: [
          {
            item_label: '1',
            description: 'Water closet',
            technical_spec: 'Rimless, 4/2.6L',
            brand: 'SORENTO',
            product_code: 'SRT-WC-01',
            quantity: '120',
            unit_price: '850.00',
            complete_set: 'c/w seat cover',
            band_label: 'TYPE A',
            is_rate_only: false,
            amount: '102000.00',
          },
          {
            item_label: '2',
            description: 'Alternate basin mixer',
            technical_spec: null,
            brand: null,
            product_code: null,
            quantity: '1',
            unit_price: '420.00',
            complete_set: null,
            band_label: 'TYPE A',
            is_rate_only: true,
            amount: null,
          },
        ],
      },
    ],
    grand_total: '235000.00',
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
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuotationSignClient token="tok-123" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('QuotationSignClient reading the quotation', () => {
  it('prints the words on a rate-only line instead of a zero amount', async () => {
    getQuotationSignPage.mockResolvedValue(page());
    renderPage();

    expect(await screen.findByText('rate only')).toBeInTheDocument();
    // The priced line still shows its money, so this is not a blanket suppression.
    expect(screen.getByText('RM 102,000.00')).toBeInTheDocument();
    // A zero would read as "free" to the person about to sign.
    expect(screen.queryByText('RM 0.00')).not.toBeInTheDocument();
  });

  it('leaves the money blank on a set component priced at nothing', async () => {
    // Quotations list the parts of a complete set on their own rows at no separate charge,
    // because the price sits on the parent. Printed as RM 0.00 they read as free products, on
    // the one page where the customer is about to commit. Not "rate only" either: that is a
    // different fact (a quoted alternate), so the words must not appear on this row.
    getQuotationSignPage.mockResolvedValue(
      page({
        scopes: [
          {
            scope_label: 'Type A',
            scope_total: '102000.00',
            lines: [
              {
                item_label: '1',
                description: 'Close coupled pedestal',
                technical_spec: null,
                brand: null,
                product_code: 'SRTWCX8608-RL',
                quantity: '894',
                unit_price: '305.55',
                complete_set: null,
                band_label: null,
                is_rate_only: false,
                amount: '273161.70',
              },
              {
                item_label: '2',
                description: 'Cistern only, no separate charge',
                technical_spec: null,
                brand: null,
                product_code: 'SRTWCY8608',
                quantity: '894',
                unit_price: '0.00',
                complete_set: null,
                band_label: null,
                is_rate_only: false,
                amount: '0.00',
              },
            ],
          },
        ],
      }),
    );
    renderPage();

    // The component is still listed, with the quantity the customer receives.
    expect(await screen.findByText('Cistern only, no separate charge')).toBeInTheDocument();
    // Both rows carry 894 (a set and its part ship together), so count rather than match one.
    expect(screen.getAllByText('894')).toHaveLength(2);
    // No money on it, in either column, and no "rate only" standing in for the blank.
    expect(screen.queryByText('RM 0.00')).not.toBeInTheDocument();
    expect(screen.queryByText('rate only')).not.toBeInTheDocument();
    // The priced parent is untouched.
    expect(screen.getByText('RM 305.55')).toBeInTheDocument();
    expect(screen.getByText('RM 273,161.70')).toBeInTheDocument();
  });

  it('heads a band once, above the lines it covers', async () => {
    getQuotationSignPage.mockResolvedValue(page());
    renderPage();

    // Both lines carry TYPE A; the label is printed for the first only.
    expect(await screen.findAllByText('TYPE A')).toHaveLength(1);
  });

  it('offers the signing affordance while the quotation is unaccepted', async () => {
    getQuotationSignPage.mockResolvedValue(page());
    renderPage();

    expect(await screen.findByRole('textbox', { name: 'Your name' })).toHaveValue('Kelly');
    expect(screen.getByRole('button', { name: 'Sign and accept' })).toBeInTheDocument();
    expect(screen.getByText('Signing below accepts this quotation.')).toBeInTheDocument();
  });
});

describe('QuotationSignClient page width', () => {
  it('takes the viewport width while the wide table scrolls inside its own gutter', async () => {
    getQuotationSignPage.mockResolvedValue(page());
    renderPage();

    // The page owns its width now that the (auth) shell hands this route the raw viewport: the
    // branded card's fixed column left empty margins either side of a nine-column quotation.
    const shell = await screen.findByTestId('quotation-sign-page');
    expect(shell.className).toContain('w-full');
    expect(shell.className).toContain('mx-auto');
    // min-w-0 + clip: whatever a scope's table does, the PAGE never drags sideways at 375px.
    expect(shell.className).toContain('min-w-0');
    expect(shell.className).toContain('overflow-x-clip');

    // And the table keeps its OWN gutter, so a phone still scrolls the columns rather than
    // having them clipped off the edge.
    const gutter = screen.getByRole('table').parentElement;
    expect(gutter?.className).toContain('overflow-x-auto');
    expect(gutter?.className).toContain('min-w-0');
  });
});

describe('QuotationSignClient once accepted', () => {
  const accepted = page({
    is_accepted: true,
    accepted_at: '2026-08-04T02:15:00',
    customer_signature: {
      id: 's2',
      signer_name: 'Kelly Tan',
      mode: 'type',
      image_data_uri: 'data:image/png;base64,CUSTOMER',
      signed_at: '2026-08-04T02:15:00',
      ip_address: '203.0.113.20',
      gps_lat: '3.1390100',
      gps_lng: '101.6868500',
      },
  });

  it('states the acceptance and its time, with nothing left to sign', async () => {
    getQuotationSignPage.mockResolvedValue(accepted);
    renderPage();

    expect(await screen.findByText('Accepted')).toBeInTheDocument();
    expect(screen.getByText(/Accepted on 04\/08\/2026, 10:15\s?am/i)).toBeInTheDocument();

    // No pad in edit mode, no name field, no commit button: signing twice is not on offer.
    expect(screen.queryByRole('textbox', { name: 'Your name' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign and accept' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('signature-pad')).not.toBeInTheDocument();
    expect(screen.queryByTestId('signature-pad-canvas')).not.toBeInTheDocument();

    // What WAS signed is shown, both halves, read-only.
    expect(screen.getByRole('img', { name: 'Kelly Tan image' })).toHaveAttribute(
      'src',
      'data:image/png;base64,CUSTOMER',
    );
    expect(screen.getByRole('img', { name: 'Ahmad Faizal image' })).toHaveAttribute(
      'src',
      'data:image/png;base64,SORENTO',
    );
  });
});

describe('QuotationSignClient signing form', () => {
  it('fills the Initials tab from the name the customer types above the pad', async () => {
    // Client feedback: the name field reads "Jayson" while the Initials tab still shows its
    // placeholder. Nothing derivable from what the signer already gave us should be asked for
    // a second time.
    getQuotationSignPage.mockResolvedValue(page({ attn_name: null }));
    renderPage();

    const nameField = await screen.findByRole('textbox', { name: 'Your name' });
    fireEvent.change(nameField, { target: { value: 'Jayson' } });

    // Radix activates a tab on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Initials' }), { button: 0 });

    expect(screen.getByRole('textbox', { name: 'Initials' })).toHaveValue('J.');
  });

  it('keeps initials the customer edited when they then correct their name', async () => {
    getQuotationSignPage.mockResolvedValue(page({ attn_name: null }));
    renderPage();

    const nameField = await screen.findByRole('textbox', { name: 'Your name' });
    fireEvent.change(nameField, { target: { value: 'Jayson' } });
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Initials' }), { button: 0 });
    fireEvent.change(screen.getByRole('textbox', { name: 'Initials' }), {
      target: { value: 'JT' },
    });

    fireEvent.change(nameField, { target: { value: 'Jayson Tan' } });

    expect(screen.getByRole('textbox', { name: 'Initials' })).toHaveValue('JT');
  });
});

describe('QuotationSignClient signature provenance', () => {
  it('reads the signing location as a place, with the coordinates still on the page', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({
        is_accepted: true,
        accepted_at: '2026-08-04T02:15:00',
        customer_signature: {
          id: 's3',
          signer_name: 'Kelly Tan',
          mode: 'draw',
          image_data_uri: 'data:image/png;base64,CUSTOMER',
          signed_at: '2026-08-04T02:15:00',
          ip_address: '203.0.113.20',
          gps_lat: '3.0392672',
          gps_lng: '101.8066021',
          // Resolved by the backend, from the same offline table the PDF renders from.
          gps_place: 'Kajang, Selangor',
        },
      }),
    );
    renderPage();

    expect(
      await screen.findByText('near Kajang, Selangor (3.03927, 101.80660)'),
    ).toBeInTheDocument();
  });
});

describe('QuotationSignClient dead link', () => {
  it('reads as a plain fact with the one action that helps', async () => {
    getQuotationSignPage.mockRejectedValue(
      new QuotationSignError(
        'This link is no longer valid. Ask your contact at Sorento to resend it.',
        404,
      ),
    );
    renderPage();

    expect(await screen.findByText('This link is no longer valid')).toBeInTheDocument();
    expect(screen.getByText('Ask your contact at Sorento to resend it.')).toBeInTheDocument();
    // Nothing to retry: the answer will not change.
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('lets a reader retry anything that is not a dead link', async () => {
    getQuotationSignPage.mockRejectedValue(new QuotationSignError('Server error.', 500));
    renderPage();

    // Longer than the default window on purpose: unlike a dead link, a 500 gets ONE automatic
    // retry (a phone on a flaky connection deserves it), and that retry's backoff is ~1s.
    expect(
      await screen.findByText('This quotation could not be loaded', {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
