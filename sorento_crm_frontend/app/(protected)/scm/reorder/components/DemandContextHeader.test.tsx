/**
 * S9 (code review, 20 Aug 2026): the window this header reports is full calendar months
 * only - it stops at the end of last month, on purpose, to stay in agreement with the
 * plan's own trend verdict (`trajectory_service.trajectory_for_run`). The label must say
 * "full months" honestly rather than implying a live trailing window through today.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DemandContextHeader } from './DemandContextHeader';

describe('DemandContextHeader', () => {
  it('renders nothing when both quantities are absent (the response predates the field)', () => {
    const { container } = render(
      <DemandContextHeader data={{ project_12m_qty: null, retail_3m_qty: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('labels the window as full months, not a live trailing count', () => {
    render(
      <DemandContextHeader
        data={{
          project_12m_qty: 120,
          retail_3m_qty: 30,
          project_window_months: 12,
          retail_window_months: 3,
        }}
      />,
    );

    expect(screen.getByText('Project, last 12 full months: 120')).toBeInTheDocument();
    expect(screen.getByText('Retail, last 3 full months: 30')).toBeInTheDocument();
  });

  it('carries a title explaining the month in progress is not counted yet', () => {
    render(
      <DemandContextHeader
        data={{ project_12m_qty: 120, retail_3m_qty: 30 }}
      />,
    );

    const badge = screen.getByText(/Project, last 12 full months/);
    expect(badge).toHaveAttribute(
      'title',
      'Full calendar months only - the month in progress is not counted yet.',
    );
  });

  it('renders a zero as a real figure, never hidden', () => {
    render(<DemandContextHeader data={{ project_12m_qty: 0, retail_3m_qty: null }} />);

    expect(screen.getByText('Project, last 12 full months: 0')).toBeInTheDocument();
    expect(screen.getByText('Retail, last 3 full months: 0')).toBeInTheDocument();
  });

  it('falls back to 12/3 months when the window fields are absent', () => {
    render(<DemandContextHeader data={{ project_12m_qty: 5, retail_3m_qty: 2 }} />);

    expect(screen.getByText('Project, last 12 full months: 5')).toBeInTheDocument();
    expect(screen.getByText('Retail, last 3 full months: 2')).toBeInTheDocument();
  });
});
