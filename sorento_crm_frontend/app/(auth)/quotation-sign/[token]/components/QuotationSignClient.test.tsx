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
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
const requestQuotationChanges = vi.fn();
const acceptQuotation = vi.fn();

vi.mock('../../services/quotationSignService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/quotationSignService')>();
  return {
    ...actual,
    getQuotationSignPage: (...args: unknown[]) => getQuotationSignPage(...args),
    requestQuotationChanges: (...args: unknown[]) => requestQuotationChanges(...args),
    acceptQuotation: (...args: unknown[]) => acceptQuotation(...args),
  };
});

import { QuotationSignClient } from './QuotationSignClient';
import { QuotationSignError } from '../../services/quotationSignService';

function page(overrides: Partial<QuotationSignPage> = {}): QuotationSignPage {
  return {
    our_ref: 'PRJQ-2026-0003-R1',
    issue_no: 1,
    amendment_request: null,
    superseded_by_ref: null,
    can_sign: true,
    sign_blocked_reason: null,
    sender_logo_url: null,
    signatory_phone: null,
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
            id: 'line-1',
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
            id: 'line-2',
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
                id: 'line-3',
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
                id: 'line-4',
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

/**
 * S17 - the customer's other answer.
 *
 * A page that only offers Accept sends anybody who wants a lower price out of the system to say
 * so. The three things pinned here are the ones that decide whether the feedback ever arrives: the
 * action has to be visible beside Accept, an EMPTY request must not be sendable, and once sent the
 * page has to settle on the new state in front of them - a form still sitting there is how a
 * customer sends the same message four times.
 */
describe('QuotationSignClient requesting changes', () => {
  const FEEDBACK = 'The townhouse rate is over our budget. Can you re-price the WC?';

  const requested = page({
    is_changes_requested: true,
    changes_requested_at: '2026-08-05T02:15:00',
    changes_requested_note: FEEDBACK,
    changes_requested_by_name: 'Kelly Tan',
  });

  // The free-text form these specs once drove ("Request changes" / "What needs to change" /
  // "Send request") is gone: owner Q5 (30 Oct) folded it into the per-line suggestions as their
  // optional note. Offering the action beside Accept, refusing an empty send and settling the
  // page on the answer are pinned for the replacement in QuotationSignAmend.test.tsx. What stays
  // here is how a request already on record (sent before the change) still reads.

  it('reads as a settled outcome afterwards, with the words quoted back', async () => {
    getQuotationSignPage.mockResolvedValue(requested);
    renderPage();

    expect(await screen.findByText('Changes requested')).toBeInTheDocument();
    expect(screen.getByText(/Sent on 05\/08\/2026, 10:15\s?am/i)).toBeInTheDocument();
    // Quoted back so the customer can see the message landed, rather than wondering.
    expect(screen.getByText(FEEDBACK)).toBeInTheDocument();

    // Nothing left to fill in: neither decision is on offer a second time.
    expect(screen.queryByRole('textbox', { name: 'What needs to change' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send request' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign and accept' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('signature-pad-canvas')).not.toBeInTheDocument();
  });

  it('shows the acceptance when the customer asked for changes and then signed anyway', async () => {
    // Allowed on purpose: refusing a signature somebody wants to give would be worse. The page
    // reports the decision that was REACHED, and the earlier request stays on the record.
    getQuotationSignPage.mockResolvedValue({
      ...requested,
      is_accepted: true,
      accepted_at: '2026-08-06T02:15:00',
      customer_signature: {
        id: 's4',
        signer_name: 'Kelly Tan',
        mode: 'type',
        image_data_uri: 'data:image/png;base64,CUSTOMER',
        signed_at: '2026-08-06T02:15:00',
        ip_address: '203.0.113.20',
        gps_lat: null,
        gps_lng: null,
      },
    });
    renderPage();

    expect(await screen.findByText('Accepted')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Request changes' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send request' })).not.toBeInTheDocument();
  });

  // The "Not ready to sign this?" row this pinned is gone: the owner's hand test (30 Oct) moved
  // "Suggest changes" into the Quotation card's header (QuotationSignAmend.test.tsx).
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


/**
 * QUOTE-SIGN-PAGE (29 Oct): logo, one number, one card of sections, the terms tick.
 */
function scopeOf(label: string, total: string, descriptions: string[]) {
  return {
    scope_label: label,
    scope_total: total,
    lines: descriptions.map((description, index) => ({
      id: `line-${index}`,
      item_label: String(index + 1),
      description,
      technical_spec: null,
      brand: null,
      product_code: null,
      quantity: '1',
      unit_price: '100.00',
      complete_set: null,
      band_label: null,
      is_rate_only: false,
      amount: '100.00',
    })),
  };
}

describe('QuotationSignClient letterhead', () => {
  it('shows one Quotation No. row with the payload ref, and keeps the Revision row', async () => {
    getQuotationSignPage.mockResolvedValue(page());
    renderPage();

    expect(await screen.findByText('Quotation No.')).toBeInTheDocument();
    expect(screen.getByText('PRJQ-2026-0003-R1')).toBeInTheDocument();
    expect(screen.queryByText('Our Ref')).not.toBeInTheDocument();
    expect(screen.getByText('Revision')).toBeInTheDocument();
    expect(screen.getByText('R1')).toBeInTheDocument();
  });

  it('shows the company logo left of the name when the payload carries one', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({ sender_logo_url: 'https://cdn.example.com/logo.png' }),
    );
    renderPage();

    const logo = await screen.findByRole('img', { name: 'Sorento Sdn Bhd logo' });
    expect(logo).toHaveAttribute('src', 'https://cdn.example.com/logo.png');
    // SN: the logo host must not learn which quotation link the reader is on.
    expect(logo).toHaveAttribute('referrerpolicy', 'no-referrer');
  });

  it('shows no logo image when the company has none', async () => {
    getQuotationSignPage.mockResolvedValue(page({ sender_logo_url: null }));
    renderPage();

    await screen.findByText('Quotation No.');
    expect(screen.queryByRole('img', { name: /logo/i })).not.toBeInTheDocument();
  });

  it('shows the sales contact as name and phone, name only, or not at all', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({ signatory_name: 'SALES REP A', signatory_phone: '+60100000001' }),
    );
    const first = renderPage();
    expect(await screen.findByText('Sales contact')).toBeInTheDocument();
    expect(screen.getByText('SALES REP A, +60100000001')).toBeInTheDocument();
    first.unmount();

    getQuotationSignPage.mockResolvedValue(
      page({ signatory_name: 'SALES REP A', signatory_phone: null }),
    );
    const second = renderPage();
    expect(await screen.findByText('Sales contact')).toBeInTheDocument();
    expect(screen.getByText('SALES REP A')).toBeInTheDocument();
    second.unmount();

    getQuotationSignPage.mockResolvedValue(page({ signatory_name: null, signatory_phone: null }));
    renderPage();
    await screen.findByText('Quotation No.');
    expect(screen.queryByText('Sales contact')).not.toBeInTheDocument();
  });
});

describe('QuotationSignClient one card of sections', () => {
  const two = page({
    scopes: [
      scopeOf('Townhouse', '200.00', ['Water closet A', 'Basin A']),
      scopeOf('Guard House', '100.00', ['Mixer B']),
    ],
    grand_total: '300.00',
  });

  it('puts the title, every section row and the total in exactly one card', async () => {
    getQuotationSignPage.mockResolvedValue(two);
    const { container } = renderPage();

    await screen.findByText('Total amount');
    const cards = Array.from(container.querySelectorAll('[data-slot="card"]')).filter((card) =>
      within(card as HTMLElement).queryByText('Total amount'),
    ) as HTMLElement[];
    expect(cards).toHaveLength(1);
    const card = within(cards[0]);
    expect(card.getByText('Quotation')).toBeInTheDocument();
    expect(card.getByText('Townhouse')).toBeInTheDocument();
    expect(card.getByText('Guard House')).toBeInTheDocument();
    expect(card.getByText('RM 300.00')).toBeInTheDocument();
  });

  it('shows each section row with its item count and total', async () => {
    getQuotationSignPage.mockResolvedValue(two);
    renderPage();

    expect(await screen.findByText('2 items')).toBeInTheDocument();
    expect(screen.getByText('1 item')).toBeInTheDocument();
    expect(screen.getByText('RM 200.00')).toBeInTheDocument();
    expect(screen.getByText('RM 100.00')).toBeInTheDocument();
  });

  it('opens a lone section on load', async () => {
    getQuotationSignPage.mockResolvedValue(page());
    renderPage();

    expect(await screen.findByText('Water closet')).toBeInTheDocument();
  });

  it('starts two sections closed, and a click opens then closes one', async () => {
    getQuotationSignPage.mockResolvedValue(two);
    renderPage();

    await screen.findByText('Townhouse');
    expect(screen.queryByText('Water closet A')).not.toBeInTheDocument();
    expect(screen.queryByText('Mixer B')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Townhouse'));
    expect(screen.getByText('Water closet A')).toBeInTheDocument();
    expect(screen.getByText('Basin A')).toBeInTheDocument();
    expect(screen.queryByText('Mixer B')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Townhouse'));
    expect(screen.queryByText('Water closet A')).not.toBeInTheDocument();
  });
});

describe('QuotationSignClient terms tick', () => {
  const TICK = 'I have read and agree to the Terms and conditions.';
  const withTerms = (overrides: Partial<QuotationSignPage> = {}) =>
    page({ terms: '<p>CLAUSE A</p>', attn_name: null, ...overrides });

  it('offers an unticked box when the issue has terms', async () => {
    getQuotationSignPage.mockResolvedValue(withTerms());
    renderPage();

    const box = await screen.findByRole('checkbox', { name: TICK });
    expect(box).not.toBeChecked();
  });

  it('names the next missing step in the hint beside Sign and accept', async () => {
    getQuotationSignPage.mockResolvedValue(withTerms());
    renderPage();

    const name = await screen.findByRole('textbox', { name: 'Your name' });
    expect(screen.getByText('Type your name and tick the terms box to accept.')).toBeInTheDocument();

    fireEvent.change(name, { target: { value: 'CONTACT B' } });
    expect(screen.getByText('Tick to agree to the terms before you accept.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: TICK }));
    expect(screen.getByText('Draw your signature to accept.')).toBeInTheDocument();
    expect(
      screen.queryByText('Tick to agree to the terms before you accept.'),
    ).not.toBeInTheDocument();
  });

  it('shows no checkbox and skips the tick step when the issue has no terms', async () => {
    getQuotationSignPage.mockResolvedValue(page({ terms: null, attn_name: null }));
    renderPage();

    await screen.findByRole('textbox', { name: 'Your name' });
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByText('Type your name to accept.')).toBeInTheDocument();
  });

  it('sends nothing and focuses the tick when a named customer taps the not-ready button', async () => {
    getQuotationSignPage.mockResolvedValue(withTerms());
    renderPage();

    fireEvent.change(await screen.findByRole('textbox', { name: 'Your name' }), {
      target: { value: 'CONTACT B' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign and accept' }));

    expect(screen.getByRole('checkbox', { name: TICK })).toHaveFocus();
    expect(acceptQuotation).not.toHaveBeenCalled();
  });

  it('focuses the name field when the not-ready button is tapped with no name', async () => {
    getQuotationSignPage.mockResolvedValue(withTerms());
    renderPage();

    const name = await screen.findByRole('textbox', { name: 'Your name' });
    fireEvent.click(screen.getByRole('button', { name: 'Sign and accept' }));

    expect(name).toHaveFocus();
    expect(acceptQuotation).not.toHaveBeenCalled();
  });

  it('sends terms_accepted: true with the signature once name and tick are in', async () => {
    HTMLCanvasElement.prototype.toDataURL = vi.fn(() => 'data:image/png;base64,TYPED');
    getQuotationSignPage.mockResolvedValue(withTerms());
    acceptQuotation.mockResolvedValue(
      withTerms({ is_accepted: true, accepted_at: '2026-08-04T02:15:00' }),
    );
    renderPage();

    fireEvent.change(await screen.findByRole('textbox', { name: 'Your name' }), {
      target: { value: 'CONTACT B' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: TICK }));
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Type' }), { button: 0 });
    fireEvent.click(screen.getByRole('button', { name: 'Sign and accept' }));

    await waitFor(() => expect(acceptQuotation).toHaveBeenCalledTimes(1));
    expect(acceptQuotation).toHaveBeenCalledWith(
      'tok-123',
      expect.objectContaining({ signer_name: 'CONTACT B', terms_accepted: true }),
    );
  });

  it('shows no checkbox once accepted', async () => {
    getQuotationSignPage.mockResolvedValue(
      withTerms({ is_accepted: true, accepted_at: '2026-08-04T02:15:00' }),
    );
    renderPage();

    await screen.findByText('Accepted');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});


describe('QuotationSignClient not-ready button (fix round 1)', () => {
  const TICK = 'I have read and agree to the Terms and conditions.';
  const NAME_HINT = 'Type your name and tick the terms box to accept.';
  const TICK_HINT = 'Tick to agree to the terms before you accept.';
  const withTerms = () => page({ terms: '<p>CLAUSE A</p>', attn_name: null });

  async function named() {
    getQuotationSignPage.mockResolvedValue(withTerms());
    renderPage();
    fireEvent.change(await screen.findByRole('textbox', { name: 'Your name' }), {
      target: { value: 'CONTACT B' },
    });
  }

  it('B2: a pad with content still cannot send without the tick, now or after unticking', async () => {
    await named();
    // Type tab: the pad now HAS content, so only the tick gate can stop the send.
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Type' }), { button: 0 });
    const box = screen.getByRole('checkbox', { name: TICK });

    fireEvent.click(screen.getByRole('button', { name: 'Sign and accept' }));
    // Settle: an async send (mutation) would land after this flush.
    await act(async () => {});
    expect(acceptQuotation).not.toHaveBeenCalled();
    expect(box).toHaveFocus();

    fireEvent.click(box);
    fireEvent.click(box);
    expect(box).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Sign and accept' }));
    await act(async () => {});
    expect(acceptQuotation).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Sign and accept' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(box).toHaveFocus();
  });

  it('R4: the not-ready button is aria-disabled and styled as such', async () => {
    await named();
    const button = screen.getByRole('button', { name: 'Sign and accept' });

    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button.className).toContain('aria-disabled:opacity-60');
  });

  it('R5: tapping with a name and no tick marks the tick row, and ticking clears it', async () => {
    await named();
    const row = screen.getByText(TICK).parentElement as HTMLElement;
    expect(row).toContainElement(screen.getByRole('checkbox', { name: TICK }));
    expect(row).not.toHaveAttribute('data-attention', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Sign and accept' }));
    expect(row).toHaveAttribute('data-attention', 'true');

    fireEvent.click(screen.getByRole('checkbox', { name: TICK }));
    expect(row).not.toHaveAttribute('data-attention', 'true');
  });

  it('R5: the hint carries an icon', async () => {
    await named();
    const hint = screen.getByText(TICK_HINT);
    expect(hint.querySelector('svg')).not.toBeNull();
  });

  it('R6: the hint is a polite live region that describes the not-ready button', async () => {
    await named();
    const hint = screen.getByText(TICK_HINT);
    expect(hint.getAttribute('id')).toBeTruthy();
    expect(hint).toHaveAttribute('aria-live', 'polite');

    const button = screen.getByRole('button', { name: 'Sign and accept' });
    expect(button).toHaveAccessibleDescription(TICK_HINT);

    fireEvent.click(screen.getByRole('checkbox', { name: TICK }));
    expect(button).toHaveAccessibleDescription('Draw your signature to accept.');

    // Ready: type tab gives the pad content, and no description is left behind.
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Type' }), { button: 0 });
    expect(screen.getByRole('button', { name: 'Sign and accept' })).toHaveAccessibleDescription('');
    expect(screen.queryByText(NAME_HINT)).not.toBeInTheDocument();
  });
});


describe('QuotationSignClient AC7 titles and location', () => {
  const sig = (name: string | null, extra: object = {}) => ({
    id: 'sx',
    signer_name: name,
    mode: 'draw',
    image_data_uri: 'data:image/png;base64,SIG',
    signed_at: '2026-08-04T02:15:00',
    ip_address: '203.0.113.9',
    gps_lat: '3.1390100',
    gps_lng: '101.6868500',
    gps_place: 'Kajang, Selangor',
    ...extra,
  });

  it('titles the Sorento card from the signature signer name', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({ sorento_signature: sig('SALES REP A'), signatory_name: 'OTHER REP' }),
    );
    renderPage();

    expect(await screen.findByText('Prepared by SALES REP A')).toBeInTheDocument();
    expect(screen.queryByText('Signed for Sorento')).not.toBeInTheDocument();
  });

  it.each([null, '', '   '])('falls back to the signatory when signer_name is %j', async (blank) => {
    getQuotationSignPage.mockResolvedValue(
      page({ sorento_signature: sig(blank), signatory_name: 'SALES REP A' }),
    );
    renderPage();

    expect(await screen.findByText('Prepared by SALES REP A')).toBeInTheDocument();
  });

  it('falls back to the company name when both names are blank, and never shows "-"', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({ sorento_signature: sig('  '), signatory_name: null }),
    );
    renderPage();

    expect(await screen.findByText('Prepared by Sorento Sdn Bhd')).toBeInTheDocument();
    expect(screen.queryByText('-', { selector: '[data-slot="card-title"]' })).not.toBeInTheDocument();
    expect(screen.queryByText('Signed for Sorento')).not.toBeInTheDocument();
  });

  it('titles the unsigned customer card "Accepted by"', async () => {
    getQuotationSignPage.mockResolvedValue(page());
    renderPage();

    expect(await screen.findByText('Accepted by')).toBeInTheDocument();
    expect(screen.queryByText('Accept this quotation')).not.toBeInTheDocument();
  });

  it('titles the accepted customer card with the signer name', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({
        is_accepted: true,
        accepted_at: '2026-08-04T02:15:00',
        customer_signature: sig('CONTACT B'),
      }),
    );
    renderPage();

    expect(await screen.findByText('Accepted by CONTACT B')).toBeInTheDocument();
    expect(screen.queryByText('Your signature')).not.toBeInTheDocument();
  });

  it('shows no GPS location anywhere, even when the payload carries coordinates', async () => {
    getQuotationSignPage.mockResolvedValue(
      page({
        sorento_signature: sig('SALES REP A'),
        is_accepted: true,
        accepted_at: '2026-08-04T02:15:00',
        customer_signature: sig('CONTACT B'),
      }),
    );
    renderPage();

    await screen.findByText('Accepted by CONTACT B');
    expect(screen.queryByText(/GPS location/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Kajang/)).not.toBeInTheDocument();
  });

  it('never asks the browser for location, and sends null coordinates on accept', async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) =>
      success({
        coords: { latitude: 3.139, longitude: 101.687 },
        timestamp: Date.now(),
      } as GeolocationPosition),
    );
    Object.defineProperty(navigator, 'geolocation', {
      value: { getCurrentPosition },
      configurable: true,
    });
    HTMLCanvasElement.prototype.toDataURL = vi.fn(() => 'data:image/png;base64,TYPED');
    getQuotationSignPage.mockResolvedValue(page({ terms: null, attn_name: null }));
    acceptQuotation.mockResolvedValue(
      page({ is_accepted: true, accepted_at: '2026-08-04T02:15:00' }),
    );
    renderPage();

    fireEvent.change(await screen.findByRole('textbox', { name: 'Your name' }), {
      target: { value: 'CONTACT B' },
    });
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Type' }), { button: 0 });
    fireEvent.click(screen.getByRole('button', { name: 'Sign and accept' }));

    await waitFor(() => expect(acceptQuotation).toHaveBeenCalledTimes(1));
    expect(acceptQuotation).toHaveBeenCalledWith(
      'tok-123',
      expect.objectContaining({ gps_lat: null, gps_lng: null }),
    );
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });
});
