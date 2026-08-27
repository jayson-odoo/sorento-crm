/**
 * The health cell, now that it reads MOVEMENT rather than margin (AC-R12).
 *
 * The pill is one of four classes; only Dead carries an ask ("Consider discontinuing");
 * the popup shows the counts the class was drawn from; and no margin figure appears
 * anywhere - a CNY cost against a MYR price was an exchange rate wearing a verdict.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanHealthCell } from './PlanHealthCell';
import { healthVerdict, type MovementClass, type ProductEconomics } from '../lib/productHealth';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

const econ = (over: Partial<ProductEconomics> = {}): ProductEconomics => ({
  product_id: 'p1',
  avg_sell_price: 90,
  sell_source: 'orders',
  sold_qty: 240,
  on_hand: 40,
  avg_monthly_out: 20,
  turnover_months: 2,
  no_movement: false,
  lifecycle_decision: null,
  lifecycle_decided_at: null,
  sold_recent_qty: 50,
  bought_recent_qty: 30,
  movement_class: 'fast_moving',
  ...over,
});

/** The four worlds, each shaped so its own class is the only one the rules can reach. */
const world: Record<MovementClass, Partial<ProductEconomics>> = {
  fast_moving: { sold_recent_qty: 50, bought_recent_qty: 30, movement_class: 'fast_moving' },
  slow_moving: { sold_recent_qty: 50, bought_recent_qty: 0, movement_class: 'slow_moving' },
  dead: { sold_recent_qty: 0, bought_recent_qty: 0, on_hand: 40, movement_class: 'dead' },
  no_history: { sold_recent_qty: 0, bought_recent_qty: 0, on_hand: 0, movement_class: 'no_history' },
};

function cellFor(klass: MovementClass, over: Partial<ProductEconomics> = {}) {
  const e = econ({ ...world[klass], ...over });
  return <PlanHealthCell health={healthVerdict(e)} econ={e} />;
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: /product health/i }));
}

describe('PlanHealthCell - the movement class', () => {
  it.each([
    ['fast_moving', 'Fast moving'],
    ['slow_moving', 'Slow moving'],
    ['dead', 'Dead'],
    ['no_history', 'No history'],
  ] as const)('reads %s as "%s"', (klass, label) => {
    render(cellFor(klass));
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('asks the buyer to reconsider a dead product, and only a dead one', () => {
    render(cellFor('dead'));
    expect(screen.getByText('Consider discontinuing')).toBeInTheDocument();
  });

  it.each(['fast_moving', 'slow_moving', 'no_history'] as const)(
    'never asks about a %s product',
    (klass) => {
      render(cellFor(klass));
      expect(screen.queryByText('Consider discontinuing')).not.toBeInTheDocument();
    },
  );

  it('renders absence when there is no movement on file, never a class', () => {
    render(<PlanHealthCell health={null} econ={null} />);
    expect(screen.queryByRole('button', { name: /product health/i })).not.toBeInTheDocument();
  });
});

describe('PlanHealthCell - no margin anywhere', () => {
  it('shows neither a margin figure nor "Margin unknown"', () => {
    render(cellFor('fast_moving', { avg_sell_price: null, sell_source: null }));
    open();

    expect(screen.queryByText(/Margin/)).not.toBeInTheDocument();
    expect(screen.queryByText('Selling price')).not.toBeInTheDocument();
    expect(screen.queryByText('Cost')).not.toBeInTheDocument();
  });

  it('shows the counts the class was drawn from instead', () => {
    render(cellFor('fast_moving'));
    open();

    expect(screen.getByText('Sold: 50 delivered in the last 3 months.')).toBeInTheDocument();
    expect(screen.getByText('Bought: 30 received in the last 6 months.')).toBeInTheDocument();
    expect(screen.getByText('On hand: 40 across every location.')).toBeInTheDocument();
  });

  it('says nothing moved rather than leaving a count out', () => {
    render(cellFor('dead'));
    open();

    expect(screen.getByText('Sold: nothing delivered in the last 3 months.')).toBeInTheDocument();
    expect(screen.getByText('Bought: nothing received in the last 6 months.')).toBeInTheDocument();
  });
});

describe('PlanHealthCell - the buyer answers', () => {
  it('names the suggestion as the verdict, not as prose', () => {
    render(cellFor('dead'));
    open();
    expect(screen.getByText('Suggestion: Discontinue')).toBeInTheDocument();
  });

  it('a living product suggests keeping it', () => {
    render(cellFor('fast_moving'));
    open();
    expect(screen.getByText('Suggestion: Keep selling')).toBeInTheDocument();
  });

  it('records the buyer choosing against the suggestion', () => {
    const onDecide = vi.fn();
    const e = econ(world.dead);
    render(<PlanHealthCell health={healthVerdict(e)} econ={e} onDecideLifecycle={onDecide} />);
    open();

    fireEvent.click(screen.getByRole('button', { name: 'Keep selling' }));
    expect(onDecide).toHaveBeenCalledWith('p1', 'keep');
  });

  it('a second click on the recorded answer withdraws it', () => {
    const onDecide = vi.fn();
    const e = econ({ ...world.dead, lifecycle_decision: 'discontinue' });
    render(<PlanHealthCell health={healthVerdict(e)} econ={e} onDecideLifecycle={onDecide} />);
    expect(screen.getByText('You chose: discontinue')).toBeInTheDocument();
    open();

    fireEvent.click(screen.getByRole('button', { name: '✓ Discontinue' }));
    expect(onDecide).toHaveBeenCalledWith('p1', null);
  });
});
