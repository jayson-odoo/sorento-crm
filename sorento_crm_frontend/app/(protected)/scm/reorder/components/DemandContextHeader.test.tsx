/**
 * S9 (code review, 20 Aug 2026): the window this header reports is full calendar months
 * only - it stops at the end of last month, on purpose, to stay in agreement with the
 * plan's own trend verdict (`trajectory_service.trajectory_for_run`). The label must say
 * "full months" honestly rather than implying a live trailing window through today.
 *
 * P5 (captain, 25 Aug): ONE badge, the drilled row's own channel. A project row is told
 * its project year and nothing else; a retail row its three months and nothing else.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DemandContextHeader } from './DemandContextHeader';

describe('DemandContextHeader', () => {
  it('renders nothing when both quantities are absent (the response predates the field)', () => {
    const { container } = render(
      <DemandContextHeader data={{ project_12m_qty: null, retail_3m_qty: null }} channel="project" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when THIS channel has no figure, even though the other does', () => {
    // The header speaks for one channel now, so the other channel's number is not a
    // stand-in for the missing one - it belongs to a different question.
    const project = render(
      <DemandContextHeader data={{ project_12m_qty: null, retail_3m_qty: 30 }} channel="project" />,
    );
    expect(project.container).toBeEmptyDOMElement();
    project.unmount();

    const retail = render(
      <DemandContextHeader data={{ project_12m_qty: 120, retail_3m_qty: null }} channel="retail" />,
    );
    expect(retail.container).toBeEmptyDOMElement();
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
        channel="project"
      />,
    );

    expect(screen.getByText('Project, last 12 full months: 120')).toBeInTheDocument();
  });

  it('shows the project window ONLY on a project row (P5)', () => {
    render(
      <DemandContextHeader
        data={{
          project_12m_qty: 120,
          retail_3m_qty: 30,
          project_window_months: 12,
          retail_window_months: 3,
        }}
        channel="project"
      />,
    );

    expect(screen.getByText('Project, last 12 full months: 120')).toBeInTheDocument();
    expect(screen.queryByText(/Retail, last/)).not.toBeInTheDocument();
  });

  it('shows the retail window ONLY on a retail row (P5)', () => {
    render(
      <DemandContextHeader
        data={{
          project_12m_qty: 120,
          retail_3m_qty: 30,
          project_window_months: 12,
          retail_window_months: 3,
        }}
        channel="retail"
      />,
    );

    expect(screen.getByText('Retail, last 3 full months: 30')).toBeInTheDocument();
    expect(screen.queryByText(/Project, last/)).not.toBeInTheDocument();
  });

  it('reads the retail window for a row that is not project (unclassified, dealer)', () => {
    // `channel` is REQUIRED - there is no channel-blind reading left to test.
    const data = { project_12m_qty: 120, retail_3m_qty: 30 };

    const unclassified = render(<DemandContextHeader data={data} channel="unclassified" />);
    expect(screen.getByText('Retail, last 3 full months: 30')).toBeInTheDocument();
    expect(screen.queryByText(/Project, last/)).not.toBeInTheDocument();
    unclassified.unmount();

    render(<DemandContextHeader data={data} channel="dealer" />);
    expect(screen.getByText('Retail, last 3 full months: 30')).toBeInTheDocument();
    expect(screen.queryByText(/Project, last/)).not.toBeInTheDocument();
  });

  it('carries a title explaining the month in progress is not counted yet', () => {
    render(<DemandContextHeader data={{ project_12m_qty: 120, retail_3m_qty: 30 }} channel="project" />);

    const badge = screen.getByText(/Project, last 12 full months/);
    expect(badge).toHaveAttribute(
      'title',
      'Full calendar months only - the month in progress is not counted yet.',
    );
  });

  it('renders a zero as a real figure, never hidden', () => {
    render(<DemandContextHeader data={{ project_12m_qty: 0, retail_3m_qty: null }} channel="project" />);

    expect(screen.getByText('Project, last 12 full months: 0')).toBeInTheDocument();
  });

  it('falls back to 12/3 months when the window fields are absent', () => {
    const project = render(
      <DemandContextHeader data={{ project_12m_qty: 5, retail_3m_qty: 2 }} channel="project" />,
    );
    expect(screen.getByText('Project, last 12 full months: 5')).toBeInTheDocument();
    project.unmount();

    render(<DemandContextHeader data={{ project_12m_qty: 5, retail_3m_qty: 2 }} channel="retail" />);
    expect(screen.getByText('Retail, last 3 full months: 2')).toBeInTheDocument();
  });
});
