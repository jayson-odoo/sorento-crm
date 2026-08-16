import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { PlanMethodologySheet } from './PlanMethodologySheet';

function openPanel() {
  fireEvent.click(screen.getByRole('button', { name: /how this plan was built/i }));
}

describe('PlanMethodologySheet', () => {
  it('renders a trigger but keeps the panel closed until clicked', () => {
    render(<PlanMethodologySheet runContext={{ dateLabel: '16 Jul 2026', timeLabel: '06:00' }} />);
    expect(screen.getByRole('button', { name: /how this plan was built/i })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens the panel with all seven methodology steps and the real rank weights', () => {
    render(<PlanMethodologySheet runContext={{ dateLabel: '16 Jul 2026', timeLabel: '06:00' }} />);
    openPanel();

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('How this plan was built')).toBeInTheDocument();

    // Every sequential step renders.
    expect(within(dialog).getAllByTestId('plan-methodology-step')).toHaveLength(7);
    expect(within(dialog).getByText('Measure demand')).toBeInTheDocument();
    expect(within(dialog).getByText('When to reorder')).toBeInTheDocument();
    expect(within(dialog).getByText('Cash funding')).toBeInTheDocument();

    // Real weights from cash_ranking.DEFAULT_WEIGHTS, with "Value" not "ABC value" (M8-F4).
    expect(within(dialog).getByText('40%')).toBeInTheDocument();
    expect(within(dialog).getByText('30%')).toBeInTheDocument();
    expect(within(dialog).getByText('Value')).toBeInTheDocument();
    expect(within(dialog).queryByText(/ABC value/i)).not.toBeInTheDocument();
  });

  it('shows the loaded run context (generated time + coverage)', () => {
    render(
      <PlanMethodologySheet
        runContext={{
          dateLabel: '16 Jul 2026',
          timeLabel: '06:00',
          warehouseCount: 1,
          warehouseCodes: ['WH-KL'],
        }}
      />,
    );
    openPanel();
    const strip = screen.getByTestId('plan-methodology-run-context');
    expect(within(strip).getByText('16 Jul 2026, 06:00')).toBeInTheDocument();
    expect(within(strip).getByText('WH-KL')).toBeInTheDocument();
  });

  it("writes this run's cash figures through the shared money format (AC-2.2)", () => {
    // The sheet used to carry its own Intl formatters and a literal "RM".
    render(
      <PlanMethodologySheet
        runContext={{ dateLabel: '16 Jul 2026', timeLabel: '06:00' }}
        facts={{
          topBuys: [],
          withinCount: 12,
          overCount: 3,
          committed: 226464,
          free: 73536,
          budget: 300000,
        }}
      />,
    );
    openPanel();
    fireEvent.click(screen.getAllByText(/See this run's numbers/)[0]);

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('RM 300,000')).toBeInTheDocument();
    expect(within(dialog).getByText('RM 226,464')).toBeInTheDocument();
    expect(within(dialog).getByText('RM 73,536')).toBeInTheDocument();
  });

  it('degrades gracefully with no run context', () => {
    render(<PlanMethodologySheet runContext={null} />);
    openPanel();
    const strip = screen.getByTestId('plan-methodology-run-context');
    expect(within(strip).getByText('Latest available snapshot')).toBeInTheDocument();
    expect(within(strip).getByText('All warehouses')).toBeInTheDocument();
    // Steps still render - methodology is static.
    expect(screen.getAllByTestId('plan-methodology-step')).toHaveLength(7);
  });
});
