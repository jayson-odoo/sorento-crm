/**
 * Which orders a planned quantity is actually for.
 *
 * > "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh"
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const useRecommendationDemand = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useRecommendationDemand: (...a: unknown[]) => useRecommendationDemand(...a),
}));

import { PlanDemandPopover } from './PlanDemandPopover';

const demand = (over: Record<string, unknown> = {}) => ({
  lines: [
    {
      so_id: 'so-uuid-414050',
      so_number: 'SO414050',
      warehouse_code: 'BRW-IB',
      is_unlocated: false,
      order_type: 'project',
      demand_class: 'project',
      order_date: '2026-07-27',
      required_date: '2026-10-12',
      qty: 2,
      customer_label: 'Vivo Homes Sdn Bhd',
      agent_label: 'Jeremy',
      unit_price: 94.5,
    },
  ],
  total: 1,
  shown: 1,
  committed_total: 2,
  unlocated_total: 0,
  locations: ['BRW-IB'],
  scope: 'warehouse',
  pool_code: null,
  channel: null,
  history_lines: [],
  history_shown: 0,
  history_total: 0,
  ...over,
});

function stub(data: unknown, extra: Record<string, unknown> = {}) {
  useRecommendationDemand.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    ...extra,
  });
}

beforeEach(() => useRecommendationDemand.mockReset());

async function open() {
  fireEvent.click(screen.getByRole('button', { name: /demand behind this row/i }));
  await waitFor(() => expect(screen.getByText(/Demand behind this row/)).toBeInTheDocument());
}

describe('PlanDemandPopover', () => {
  it('does not fetch until it is opened', async () => {
    // The query lives inside the opened panel, so a closed row holds no subscription at
    // all - on a full plan that is hundreds of them for panels nobody opened.
    stub(demand());
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);

    expect(useRecommendationDemand).not.toHaveBeenCalled();

    await open();
    expect(useRecommendationDemand).toHaveBeenCalledWith(
      'run-1', 'rec-1', true, undefined, undefined,
    );
  });

  it('names the location the ORDER was for, which is the whole question', async () => {
    stub(demand());
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText('SO414050')).toBeInTheDocument();
    expect(screen.getByText('BRW-IB')).toBeInTheDocument();
    expect(screen.getByText('2 committed at BRW-IB')).toBeInTheDocument();
  });

  it('names the POOL when the plan netted the pool together', async () => {
    // AC-1.2: the number is still the row's own, but it was built over the pool, and a
    // list of siblings the buyer never ordered for has to say why it is there.
    stub(
      demand({
        committed_total: 6683,
        locations: ['BRW-BB', 'BRW-IB'],
        scope: 'pool',
        pool_code: 'BRW',
      }),
    );
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(
      screen.getByText('6,683 committed at BRW-BB, BRW-IB (pool BRW)'),
    ).toBeInTheDocument();
  });

  it('says which part of it nobody located', async () => {
    stub(
      demand({
        unlocated_total: 419,
        committed_total: 420,
        locations: ['BRW-IB', 'No location'],
        lines: [{ ...demand().lines[0], warehouse_code: null, is_unlocated: true, qty: 419 }],
      }),
    );
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(
      screen.getByText('420 committed at BRW-IB, No location, incl. 419 unlocated'),
    ).toBeInTheDocument();
    expect(screen.getByText('No location')).toBeInTheDocument();
  });

  it('names who ordered each line, who sold it, and what they pay', async () => {
    stub(demand());
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText(/Vivo Homes Sdn Bhd/)).toBeInTheDocument();
    expect(screen.getByText(/Jeremy/)).toBeInTheDocument();
    expect(screen.getByText('RM 94.50')).toBeInTheDocument();
  });

  it('keeps the honest fallbacks the backend sends, and shows no price when there is none', async () => {
    // "Unnamed customer" is retired: a debtor code IS an attribution, and an order that
    // names nobody is a fact about the order rather than a missing value.
    stub(
      demand({
        lines: [
          { ...demand().lines[0], customer_label: 'Debtor 300-R009', unit_price: null },
        ],
      }),
    );
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText(/Debtor 300-R009/)).toBeInTheDocument();
    expect(screen.queryByText(/^RM /)).not.toBeInTheDocument();
  });

  it('distinguishes project from retail', async () => {
    stub(demand({ lines: [{ ...demand().lines[0], order_type: 'retail' }] }));
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText('retail')).toBeInTheDocument();
  });

  it('says a forecast-raised buy has no order behind it, rather than showing nothing', async () => {
    stub(demand({ lines: [], total: 0, shown: 0, committed_total: 0, locations: [] }));
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText(/raised from forecast demand/i)).toBeInTheDocument();
  });

  // 21 Aug follow-up: "SO numbers in both views become hyperlinks to the sales order's
  // own record" - `/scm/sales-orders/{so_id}`, the same target `SalesOrdersList` itself
  // links a row to.
  describe('the SO number link', () => {
    it('links to the sales order record when the line carries so_id', async () => {
      stub(demand());
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      const link = screen.getByRole('link', { name: 'SO414050' });
      expect(link).toHaveAttribute('href', '/scm/sales-orders/so-uuid-414050');
    });

    it('falls back to plain text on a cached response predating so_id', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], so_id: undefined }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.queryByRole('link', { name: 'SO414050' })).not.toBeInTheDocument();
      expect(screen.getByText('SO414050')).toBeInTheDocument();
    });
  });

  // SF-8: the source chip (SO / OI / OI confirmed) and its title, per line.
  describe('source chip', () => {
    it('renders SO with "Direct sales order" for a direct sales-order line', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: 'sales_order' }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      const chip = screen.getByText('SO');
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveAttribute('title', 'Direct sales order');
    });

    it('renders "OI import" with "Order created by the Order Inquiry import" for a sheet-leg line', async () => {
      // Defect B: "OI" used to claim a live worklist entry off `demand_origin` alone -
      // this is a stamp on the ORDER, not a fact about whether a row still exists.
      stub(demand({ lines: [{ ...demand().lines[0], source: 'order_inquiry' }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      const chip = screen.getByText('OI import');
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveAttribute('title', 'Order created by the Order Inquiry import');
    });

    it('renders "OI confirmed" with "Confirmed for buy by CS" for a CS-confirmed line', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: 'order_inquiry_confirmed' }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      const chip = screen.getByText('OI confirmed');
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveAttribute('title', 'Confirmed for buy by CS');
    });

    it('renders no chip at all when the line carries no source', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: null }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.queryByText('SO')).not.toBeInTheDocument();
      expect(screen.queryByText('OI')).not.toBeInTheDocument();
      expect(screen.queryByText('OI confirmed')).not.toBeInTheDocument();
    });
  });

  // SF-8 / N-6: the channel-split totals line under the scope sentence.
  describe('the totals line (project/retail/unclassified split)', () => {
    it('renders the split when the payload carries any of the three totals', async () => {
      stub(demand({ project_total: 6, retail_total: 4, unclassified_total: 0 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.getByText('Project 6 - Retail 4')).toBeInTheDocument();
    });

    it('adds the Unclassified part only when it is nonzero', async () => {
      stub(demand({ project_total: 6, retail_total: 4, unclassified_total: 3 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.getByText('Project 6 - Retail 4 - Unclassified 3')).toBeInTheDocument();
    });

    it('hides the totals line entirely on a legacy payload carrying none of the three fields', async () => {
      // `demand()` is the legacy fixture shape - no project_total/retail_total/unclassified_total.
      stub(demand());
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.queryByText(/^Project /)).not.toBeInTheDocument();
    });
  });

  // Defect B: the worklist click-through must not promise a screen that will be empty.
  // 21 Aug follow-up: it is now a SEPARATE "OI worklist" link beside the chips, never on
  // the SO number itself (which links to the sales order's own record instead).
  describe('the Order Inquiry worklist link', () => {
    it('links a sheet-leg line when a live inquiry row exists', async () => {
      stub(
        demand({
          lines: [{ ...demand().lines[0], source: 'order_inquiry', has_inquiry_row: true }],
        }),
      );
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.getByRole('link', { name: 'OI worklist' })).toBeInTheDocument();
    });

    it('does not link a sheet-leg line when no inquiry row exists', async () => {
      // The common case, measured live: 605 core orders carry the `order_inquiry`
      // provenance stamp, 7 still have a row. Linking on the stamp alone sent a captain
      // to a worklist filtered to nothing.
      stub(
        demand({
          lines: [{ ...demand().lines[0], source: 'order_inquiry', has_inquiry_row: false }],
        }),
      );
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.queryByRole('link', { name: 'OI worklist' })).not.toBeInTheDocument();
      expect(screen.getByText('SO414050')).toBeInTheDocument();
    });

    it('always links the confirmed leg, which is built from a live row', async () => {
      stub(
        demand({
          lines: [
            { ...demand().lines[0], source: 'order_inquiry_confirmed', has_inquiry_row: true },
          ],
        }),
      );
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.getByRole('link', { name: 'OI worklist' })).toBeInTheDocument();
    });

    it('does not link a direct sales-order line', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: 'sales_order' }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.queryByRole('link', { name: 'OI worklist' })).not.toBeInTheDocument();
    });
  });

  // Defect A: a `channel` prop narrows the fetch AND says which channel it opened.
  describe('a channel-scoped trigger', () => {
    it('passes the channel through to the fetch, keyed for its own cache entry', async () => {
      stub(demand({ channel: 'project' }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" />);
      fireEvent.click(screen.getByRole('button', { name: /project demand behind this row/i }));
      await screen.findByText('Project demand behind this row');

      expect(useRecommendationDemand).toHaveBeenCalledWith(
        'run-1', 'rec-1', true, 'project', undefined,
      );
    });

    it('says which channel the header is showing', async () => {
      stub(demand({ channel: 'retail', committed_total: 3092 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="retail" />);
      fireEvent.click(screen.getByRole('button', { name: /retail demand behind this row/i }));

      expect(await screen.findByText('Retail demand behind this row')).toBeInTheDocument();
      expect(screen.getByText('3,092 committed at BRW-IB')).toBeInTheDocument();
    });

    it('hides the multi-channel totals line - the header already says which one this is', async () => {
      stub(demand({ channel: 'project', project_total: 5395, retail_total: 3092 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" />);
      fireEvent.click(screen.getByRole('button', { name: /project demand behind this row/i }));
      await screen.findByText('Project demand behind this row');

      expect(screen.queryByText(/^Project \d/)).not.toBeInTheDocument();
    });

    it('names the channel in the empty state instead of the generic forecast copy', async () => {
      stub(demand({ channel: 'retail', lines: [], total: 0, shown: 0, committed_total: 0 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="retail" />);
      fireEvent.click(screen.getByRole('button', { name: /retail demand behind this row/i }));

      expect(
        await screen.findByText(/No open retail order line sits behind this quantity/i),
      ).toBeInTheDocument();
    });
  });

  // 21 Aug live-test follow-up: "on the product row you show me the history, not the
  // demand" - `scope="product"` switches the WHOLE body to the order-history section,
  // never stacking it with the open-demand list.
  describe('a product-wide trigger (scope="product") opens the HISTORY view, not the demand list', () => {
    const history = (over: Record<string, unknown> = {}) =>
      demand({
        channel: 'project',
        project_window_months: 12,
        project_12m_qty: 40,
        history_lines: [
          {
            so_id: 'so-uuid-hist-1',
            so_number: 'SOHIST-1',
            order_date: '2026-06-01',
            demand_class: 'project',
            qty: 20,
            delivered: true,
            customer_label: 'Vivo Homes Sdn Bhd',
            agent_label: 'Jeremy',
            unit_price: 45,
          },
        ],
        history_shown: 1,
        history_total: 1,
        ...over,
      });

    it('labels the trigger as order history, not demand', () => {
      stub(history());
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" scope="product" />);

      expect(
        screen.getByRole('button', { name: 'Project order history' }),
      ).toBeInTheDocument();
    });

    it('fetches with scope="product", keyed for its own cache entry', async () => {
      stub(history());
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" scope="product" />);
      fireEvent.click(screen.getByRole('button', { name: 'Project order history' }));
      await screen.findByText('Project order history');

      expect(useRecommendationDemand).toHaveBeenCalledWith(
        'run-1', 'rec-1', true, 'project', 'product',
      );
    });

    it('renders the history lines - SO, delivered marker, date, customer, agent, price, qty', async () => {
      stub(history());
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" scope="product" />);
      fireEvent.click(screen.getByRole('button', { name: 'Project order history' }));
      await screen.findByText('Project order history');

      expect(screen.getByRole('link', { name: 'SOHIST-1' })).toHaveAttribute(
        'href', '/scm/sales-orders/so-uuid-hist-1',
      );
      expect(screen.getByText('Delivered')).toBeInTheDocument();
      expect(screen.getByText('2026-06-01')).toBeInTheDocument();
      expect(screen.getByText(/Vivo Homes Sdn Bhd/)).toBeInTheDocument();
      expect(screen.getByText(/Jeremy/)).toBeInTheDocument();
      expect(screen.getByText('RM 45.00')).toBeInTheDocument();
      expect(screen.getByText('20')).toBeInTheDocument();
    });

    it('never renders the open-demand list under a product-wide trigger', async () => {
      // `history()` carries no `lines` override, so the demand fixture's own
      // "SO414050"/"Vivo Homes" line would show up here if the demand body leaked in.
      stub(history());
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" scope="product" />);
      fireEvent.click(screen.getByRole('button', { name: 'Project order history' }));
      await screen.findByText('Project order history');

      expect(screen.queryByText('SO414050')).not.toBeInTheDocument();
      expect(screen.queryByText(/committed at/)).not.toBeInTheDocument();
    });

    it('shows an open (not delivered) badge for a still-open history order', async () => {
      const baseHistoryLine = history().history_lines as Record<string, unknown>[];
      stub(
        history({
          history_lines: [{ ...baseHistoryLine[0], delivered: false }],
        }),
      );
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" scope="product" />);
      fireEvent.click(screen.getByRole('button', { name: 'Project order history' }));
      await screen.findByText('Project order history');

      expect(screen.getByText('Open')).toBeInTheDocument();
      expect(screen.queryByText('Delivered')).not.toBeInTheDocument();
    });

    it('names the window in the empty state when there is no history', async () => {
      stub(history({ history_lines: [], history_shown: 0, history_total: 0 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" scope="product" />);
      fireEvent.click(screen.getByRole('button', { name: 'Project order history' }));

      expect(
        await screen.findByText(/No project orders in the last 12 full months/i),
      ).toBeInTheDocument();
    });

    it('shows "showing X of Y" only when the uncapped total exceeds what is shown', async () => {
      stub(history({ history_shown: 1, history_total: 3 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" channel="project" scope="product" />);
      fireEvent.click(screen.getByRole('button', { name: 'Project order history' }));

      expect(await screen.findByText('Showing 1 of 3 orders.')).toBeInTheDocument();
    });
  });
});
