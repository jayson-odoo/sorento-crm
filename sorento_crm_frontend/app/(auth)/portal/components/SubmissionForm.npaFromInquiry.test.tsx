/**
 * NPA-FROM-SI: the portal stock inquiry view. Purchasing's ask shows as a banner and, while it is
 * unanswered, the page's one primary button starts a New Product Application from the inquiry. A
 * tab lists the applications raised from it. Other kinds are untouched.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

import * as portalClient from '../lib/portal-client';
import { SubmissionClientProvider } from '../lib/submission-client';
import { SubmissionForm } from './SubmissionForm';
import { CMP_DETAIL, ME, SI_DETAIL } from './__fixtures__/crmSubmissionApi';

const ASK = 'Purchasing asks you to create a New Product Application.';
const CTA = 'Create new product application';

function renderKind(
  kind: 'stock_inquiry' | 'complaint',
  detail: Record<string, unknown>,
  slug?: string,
) {
  const client = {
    ...portalClient,
    fetchMe: vi.fn(async () => ({ ...ME })),
    fetchSubmission: vi.fn(async () => detail as never),
    fetchSubmissionNeighbours: vi.fn(async () => ({
      prev_id: null,
      next_id: null,
      position: 1,
      total: 1,
    })),
    fetchRevisions: vi.fn(async () => []),
    fetchSubmissionComments: vi.fn(async () => []),
    lookupSet: vi.fn(async () => ({ options: [], defaultValue: null })),
    lookupProducts: vi.fn(async () => []),
    lookupDebtors: vi.fn(async () => []),
  };
  render(
    <SubmissionClientProvider client={client as never}>
      <SubmissionForm kind={kind} submissionId={String(detail.id)} slug={slug} />
    </SubmissionClientProvider>,
  );
}

const responded = (over: Record<string, unknown> = {}) =>
  SI_DETAIL({
    id: 'si-5',
    status: 'responded',
    is_draft: false,
    is_editable: false,
    npa_requested: true,
    npa_form_visible: true,
    new_product_applications: [],
    ...over,
  });

describe('portal stock inquiry: ask banner and Create button', () => {
  it('shows the blue ask and the Create button while asked and no live application', async () => {
    renderKind('stock_inquiry', responded());
    expect(await screen.findByText(ASK)).toBeInTheDocument();
    const cta = screen.getByRole('link', { name: CTA });
    expect(cta).toHaveAttribute(
      'href',
      '/portal/new_product_application/new?stock_inquiry_id=si-5',
    );
  });

  it('keeps the slug in the link on the slug tree', async () => {
    renderKind('stock_inquiry', responded(), 'acme');
    const cta = await screen.findByRole('link', { name: CTA });
    expect(cta.getAttribute('href')).toBe(
      '/portal/c/acme/new_product_application/new?stock_inquiry_id=si-5',
    );
  });

  it('has neither once a live application exists', async () => {
    renderKind(
      'stock_inquiry',
      responded({
        new_product_applications: [
          {
            id: 'a-1',
            application_no: 'NPA-000001',
            status: 'submitted',
            status_label: 'Submitted',
            created_at: '2026-11-03T02:00:00',
            created_codes: [],
          },
        ],
      }),
    );
    await screen.findByRole('tab', { name: /new product applications \(1\)/i });
    expect(screen.queryByText(ASK)).toBeNull();
    expect(screen.queryByRole('link', { name: CTA })).toBeNull();
  });

  it('has neither when purchasing did not ask', async () => {
    renderKind('stock_inquiry', responded({ npa_requested: false }));
    await screen.findByRole('tab', { name: /new product applications \(0\)/i });
    expect(screen.queryByText(ASK)).toBeNull();
    expect(screen.queryByRole('link', { name: CTA })).toBeNull();
  });

  it('has no Create button before the inquiry is responded', async () => {
    renderKind('stock_inquiry', responded({ status: 'pending_purchasing' }));
    await screen.findByRole('tab', { name: /new product applications/i });
    expect(screen.queryByRole('link', { name: CTA })).toBeNull();
  });

  it('turns green with the new code once one was created', async () => {
    renderKind(
      'stock_inquiry',
      responded({
        new_product_applications: [
          {
            id: 'a-1',
            application_no: 'NPA-000001',
            status: 'completed',
            status_label: 'Completed',
            created_at: '2026-11-03T02:00:00',
            created_codes: [
              {
                product_code: 'XY-1-69',
                current_codes: ['XY-1'],
                created_at: '2026-11-03T02:00:00',
              },
            ],
          },
        ],
      }),
    );
    expect(
      await screen.findByText('New code XY-1-69 created on 03/11/2026 (NPA-000001).'),
    ).toBeInTheDocument();
    expect(screen.queryByText(ASK)).toBeNull();
  });
});

describe('portal stock inquiry: New product applications tab', () => {
  it('lists the applications, the number linking to the portal view', async () => {
    renderKind(
      'stock_inquiry',
      responded({
        new_product_applications: [
          {
            id: 'a-1',
            application_no: 'NPA-000001',
            status: 'submitted',
            status_label: 'Submitted',
            created_at: '2026-11-03T02:00:00',
            created_codes: [],
          },
        ],
      }),
    );
    fireEvent.mouseDown(
      await screen.findByRole('tab', { name: /new product applications \(1\)/i }),
    );
    const link = await screen.findByRole('link', { name: 'NPA-000001' });
    expect(link).toHaveAttribute('href', '/portal/new_product_application/a-1');
    expect(screen.getAllByText('Submitted').length).toBeGreaterThan(0);
  });

  it('shows the empty state when there are none', async () => {
    renderKind('stock_inquiry', responded({ npa_requested: false }));
    fireEvent.mouseDown(
      await screen.findByRole('tab', { name: /new product applications \(0\)/i }),
    );
    expect(await screen.findByText('No new product applications')).toBeInTheDocument();
    expect(
      screen.getByText('Applications created from this inquiry show here.'),
    ).toBeInTheDocument();
  });

  it('is not on other kinds', async () => {
    renderKind('complaint', CMP_DETAIL({ status: 'submitted', is_draft: false, is_editable: false }));
    await screen.findByRole('tab', { name: /^Revisions/ });
    expect(screen.queryByRole('tab', { name: /new product applications/i })).toBeNull();
    expect(screen.queryByRole('link', { name: CTA })).toBeNull();
  });
});

describe('portal stock inquiry: npa_form_visible (the contact holds the NPA form)', () => {
  const created = [
    {
      id: 'a-1',
      application_no: 'NPA-000001',
      status: 'completed',
      status_label: 'Completed',
      created_at: '2026-11-03T02:00:00',
      created_codes: [
        { product_code: 'XY-1-69', current_codes: ['XY-1'], created_at: '2026-11-03T02:00:00' },
      ],
    },
  ];

  it('false: no Create button, no tab and no ask banner even while asked', async () => {
    renderKind('stock_inquiry', responded({ npa_form_visible: false, npa_requested: true }));
    await screen.findByRole('tab', { name: /^Revisions/ });
    expect(screen.queryByRole('link', { name: CTA })).toBeNull();
    expect(screen.queryByRole('tab', { name: /new product applications/i })).toBeNull();
    expect(screen.queryByText(ASK)).toBeNull();
  });

  it('false: no green created banner either', async () => {
    renderKind(
      'stock_inquiry',
      responded({ npa_form_visible: false, new_product_applications: created }),
    );
    await screen.findByRole('tab', { name: /^Revisions/ });
    expect(screen.queryByText(/New code XY-1-69 created/)).toBeNull();
    expect(screen.queryByRole('tab', { name: /new product applications/i })).toBeNull();
  });

  it('true: the ask, the button and the tab are there as before', async () => {
    renderKind('stock_inquiry', responded({ npa_form_visible: true }));
    expect(await screen.findByText(ASK)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: CTA })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /new product applications \(0\)/i })).toBeInTheDocument();
  });

  it('true: still no button before the inquiry is responded', async () => {
    renderKind(
      'stock_inquiry',
      responded({ npa_form_visible: true, status: 'pending_purchasing' }),
    );
    await screen.findByRole('tab', { name: /new product applications/i });
    expect(screen.queryByRole('link', { name: CTA })).toBeNull();
  });
});

// Crew 375 px pass (8 Nov): gear + Create + the "< 3/12 >" pager made the header 426 px wide.
// jsdom cannot measure, so the layout contract is pinned: the action row wraps, and on a phone
// the Create button takes its own full-width row (it shares the row from sm up).
describe('portal stock inquiry: header fits a 375 px phone', () => {
  it('the header action row wraps and the Create button takes its own row on a phone', async () => {
    renderKind('stock_inquiry', responded({ npa_form_visible: true }));
    const link = await screen.findByRole('link', { name: CTA });
    expect(link.className).toMatch(/\bbasis-full\b/);
    expect(link.className).toMatch(/\bsm:basis-auto\b/);
    const row = link.parentElement as HTMLElement;
    expect(row.className).toMatch(/\bflex-wrap\b/);
  });
});
