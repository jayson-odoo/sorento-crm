/**
 * The third suggestion on a row (S13f): the AutoCount level to set.
 *
 * The one rule: it is an ASK. The engine never changes a level, so the cell must read as
 * "set it to 24" with the arithmetic behind it - never as something already done.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanLevelCell } from './PlanLevelCell';
import type { LevelSuggestion } from '../lib/levelSuggestion';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

const suggestion = (over: Partial<LevelSuggestion> = {}): LevelSuggestion => ({
  product_id: 'p1',
  warehouse_id: 'w1',
  product_code: 'SRT-100',
  product_name: 'Basin',
  warehouse_code: 'BRW',
  warehouse_name: 'Branch West',
  current_level: 20,
  current_source: 'autocount',
  suggested_level: 24,
  suggested_at: '2026-08-10T00:00:00',
  basis: {
    months: [],
    months_studied: 3,
    total_qty: 36,
    avg_monthly: 12,
    cover_months: 2,
    raw_level: 24,
    moq: null,
    order_multiple: null,
    trend: 'rising',
    no_movement: false,
  },
  ...over,
});

describe('PlanLevelCell', () => {
  it('asks for the change with both numbers on the row', () => {
    render(<PlanLevelCell suggestion={suggestion()} />);

    expect(screen.getByText('Set AutoCount level to 24')).toBeInTheDocument();
    expect(screen.getByText('now 20')).toBeInTheDocument();
  });

  it('confirms a level that still fits, quietly', () => {
    render(<PlanLevelCell suggestion={suggestion({ suggested_level: 20 })} />);

    expect(screen.getByText('Level 20 still fits')).toBeInTheDocument();
  });

  it('opens the arithmetic, which ends at our own orders', () => {
    render(<PlanLevelCell suggestion={suggestion()} />);

    fireEvent.click(screen.getByRole('button', { name: /level suggestion/i }));

    expect(screen.getByText(/Averaged 12 a month over the last 3 months/)).toBeInTheDocument();
    expect(screen.getByText(/rounds up/)).toBeInTheDocument();
    expect(screen.getByText(/Based on our own outgoing orders only/)).toBeInTheDocument();
  });

  it('renders absence when there is no suggestion, never a zero', () => {
    render(<PlanLevelCell suggestion={undefined} />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
