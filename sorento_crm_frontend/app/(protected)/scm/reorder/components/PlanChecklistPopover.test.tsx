import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PlanChecklistPopover } from './PlanChecklistPopover';
import type { ReorderRecommendation } from '../types/reorder.types';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1',
    sku: 'SKU-1',
    segment: 'dealer',
    on_hand: 8,
    incoming_spo: 30,
    outstanding_po: 12,
    outstanding_sales: 2,
    net_position: 48,
    reorder_level: 20,
    reorder_level_source: 'manual',
    moq: 10,
    order_multiple: 4,
    last_purchase_cost: 33,
    last_purchase_currency: 'USD',
    last_purchase_date: '2026-05-02',
    last_purchase_basis: 'own_segment',
    ...over,
  } as unknown as ReorderRecommendation;
}

const open = () => fireEvent.click(screen.getByRole('button', { name: /what the plan checked/i }));

describe('PlanChecklistPopover', () => {
  it('keeps incoming stock and the outstanding PO book apart', () => {
    render(<PlanChecklistPopover rec={rec()} />);
    open();
    expect(screen.getByText('Incoming (SPO)')).toBeInTheDocument();
    expect(screen.getByText('Outstanding PO')).toBeInTheDocument();
  });

  it('shows the figures the buyer used to look up by hand', () => {
    render(<PlanChecklistPopover rec={rec()} />);
    open();
    for (const label of ['On hand', 'Outstanding sales', 'Net position', 'Reorder level', 'MoQ']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('names the segment the row belongs to', () => {
    render(<PlanChecklistPopover rec={rec({ segment: 'project' })} />);
    open();
    expect(screen.getByText('project')).toBeInTheDocument();
  });

  it('says a price is not attributed to a segment rather than implying it is', () => {
    render(<PlanChecklistPopover rec={rec({ last_purchase_basis: 'unattributed' })} />);
    open();
    expect(screen.getByText(/not attributed to a segment/i)).toBeInTheDocument();
  });

  it('adds no such note when the price really is this segment’s own', () => {
    render(<PlanChecklistPopover rec={rec()} />);
    open();
    expect(screen.queryByText(/not attributed to a segment/i)).not.toBeInTheDocument();
  });

  it('says never purchased instead of showing an empty price', () => {
    render(
      <PlanChecklistPopover
        rec={rec({ last_purchase_basis: 'never_purchased', last_purchase_cost: null })}
      />,
    );
    open();
    expect(screen.getByText(/never purchased/i)).toBeInTheDocument();
    expect(screen.queryByText('Bought on')).not.toBeInTheDocument();
  });

  it('fetches nothing: every figure is already frozen on the row', () => {
    const spy = vi.spyOn(globalThis, 'fetch' as never);
    render(<PlanChecklistPopover rec={rec()} />);
    open();
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
