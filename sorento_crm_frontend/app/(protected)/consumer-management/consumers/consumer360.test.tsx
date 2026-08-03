/**
 * Consumer 360 - the two things this page must not get wrong.
 *
 * 1. **"Value hidden" and "no total on the receipt" are different sentences.** The API omits
 *    `total_value` for a reader without `consumers.purchase_value.view` and sends `null` when
 *    the receipt genuinely showed no total (AC-L24). The seed grants that permission to
 *    nobody, so the omitted case is the DEFAULT one this page renders. Drawing a blank or a
 *    zero for it would tell a CS agent the dealer sold it for nothing.
 *
 * 2. **A merged profile offers the survivor.** The losing row is retained pointing at the
 *    survivor precisely so "where did this consumer go" is answerable (AC-L10). Rendering it
 *    as an error, or as an empty profile, throws away the one thing it exists to say.
 *
 * Empty sections are covered too: a consumer with no purchases is the ordinary state of a
 * provisional profile, and the section still has to render with a next step rather than
 * vanish.
 */
import { Suspense } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import Consumer360Page from './[id]/page';
import type { Consumer360 } from './services/consumerService';

const getConsumer360 = vi.fn();

vi.mock('./services/consumerService', () => ({
  getConsumer360: (...args: unknown[]) => getConsumer360(...args),
}));

function baseData(overrides: Partial<Consumer360> = {}): Consumer360 {
  return {
    profile: {
      id: 'p1',
      full_name: 'Ong Mei Ling',
      phone_e164: '+60127773344',
      email: null,
      respond_contact_id: null,
      is_provisional: false,
      confirmed_at: null,
      consent_purpose: 'warranty_service',
      consent_notice_version: 'consumer_intake.v1',
      consent_recorded_at: '2026-08-03T01:00:00',
      anonymised_at: null,
      merged_into_id: null,
      created_at: '2026-08-01T01:00:00',
    },
    merged_into_id: null,
    purchases: [],
    complaints: [],
    counts: { purchases: 0, complaints: 0 },
    ...overrides,
  };
}

function purchase(extra: Record<string, unknown>) {
  return {
    id: 'pu1',
    purchase_number: 'CP2025-0001',
    purchase_date: '2025-10-16',
    purchase_date_source: 'stated',
    dealer_document_number: 'KCS-2112-0054',
    customer_id: null,
    proof_attachment_id: null,
    registered_at: null,
    registration_source: 'self',
    dedupe_pending: false,
    lines: [],
    ...extra,
  };
}

async function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // Wrapped in `act` and awaited: `use(params)` suspends until the promise settles, and
  // without flushing microtasks inside act the tree never gets past the fallback.
  let result: ReturnType<typeof render> | undefined;
  await act(async () => {
    result = render(
    <QueryClientProvider client={client}>
      {/* `use(params)` unwraps a promise, which suspends until it settles. Next supplies
          the boundary in the app router; the test has to supply its own or nothing ever
          renders and every assertion fails identically. */}
      <Suspense fallback={<div>loading</div>}>
        <Consumer360Page params={Promise.resolve({ id: 'p1' })} />
      </Suspense>
    </QueryClientProvider>,
    );
  });
  return result!;
}

describe('Consumer 360', () => {
  it('says the value is hidden when the field is absent', async () => {
    // No `total_value` key at all - what a reader without the permission receives, which
    // is every reader by default.
    getConsumer360.mockResolvedValue(
      baseData({ purchases: [purchase({})] as never, counts: { purchases: 1, complaints: 0 } }),
    );
    await renderPage();
    await waitFor(() => expect(screen.getByText(/value hidden/i)).toBeInTheDocument());
  });

  it('distinguishes a receipt that showed no total from a value it may not see', async () => {
    // `null` present means the receipt itself carried no total. A different fact, and the
    // one a CS agent can act on by asking for a better photo.
    getConsumer360.mockResolvedValue(
      baseData({
        purchases: [purchase({ total_value: null, currency: null })] as never,
        counts: { purchases: 1, complaints: 0 },
      }),
    );
    await renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no total on the receipt/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/value hidden/i)).not.toBeInTheDocument();
  });

  it('shows the value when the reader is permitted', async () => {
    getConsumer360.mockResolvedValue(
      baseData({
        purchases: [purchase({ total_value: 1250, currency: 'MYR' })] as never,
        counts: { purchases: 1, complaints: 0 },
      }),
    );
    await renderPage();
    await waitFor(() => expect(screen.getByText(/MYR 1250/)).toBeInTheDocument());
  });

  it('offers the surviving profile instead of an error when this one was merged', async () => {
    getConsumer360.mockResolvedValue(baseData({ merged_into_id: 'p2' }));
    await renderPage();
    await waitFor(() => expect(screen.getByText(/was merged/i)).toBeInTheDocument());
    expect(screen.getByRole('link', { name: /surviving profile/i })).toHaveAttribute(
      'href',
      '/consumer-management/consumers/p2',
    );
  });

  it('renders every section with a next step when the consumer has nothing yet', async () => {
    // The ordinary state of a provisional profile. Hiding the sections would leave a CS
    // agent unsure whether the data is missing or the page is broken.
    getConsumer360.mockResolvedValue(baseData());
    await renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no purchases recorded yet/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/no complaints from this consumer/i)).toBeInTheDocument();
    expect(screen.getByText(/lodges one through the portal/i)).toBeInTheDocument();
  });

  it('shows which consent wording the person was actually shown', async () => {
    // "They agreed" without a version answers nothing: PDPA s.7(2) requires the notice in
    // both languages, so the question is always WHICH notice.
    getConsumer360.mockResolvedValue(baseData());
    await renderPage();
    await waitFor(() => expect(screen.getByText('consumer_intake.v1')).toBeInTheDocument());
  });
});
