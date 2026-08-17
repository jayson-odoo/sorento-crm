/**
 * The history surface. What is pinned here is the SHAPE, because the shape is the decision:
 * a history is a timeline (parcel tracking, Sheets version history), and everything else that
 * lists rows is a DataGrid. See ADR-PRODUCT-STANDARDS 1d-bis.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EventTimeline, type TimelineEvent } from './EventTimeline';

function event(overrides: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    id: 'e1',
    title: 'Stage changed',
    at: '2026-08-03T06:21:17',
    ...overrides,
  };
}

describe('EventTimeline', () => {
  it('says the day once, above the events that happened on it', () => {
    render(
      <EventTimeline
        events={[
          event({ id: 'e1', at: '2026-08-03T06:21:17' }),
          event({ id: 'e2', title: 'Quotation revised', at: '2026-08-03T02:10:00' }),
          event({ id: 'e3', title: 'Lead recorded', at: '2026-08-01T09:00:00' }),
        ]}
      />,
    );

    // Two days, two headings - not three date stamps.
    expect(screen.getByText('03/08/2026')).toBeInTheDocument();
    expect(screen.getByText('01/08/2026')).toBeInTheDocument();
    expect(screen.getAllByText('03/08/2026')).toHaveLength(1);
  });

  it('stamps each step with an absolute time, never a relative one', () => {
    render(<EventTimeline events={[event()]} />);

    // "3h ago" rots while the page is open and cannot be compared between two rows.
    expect(screen.queryByText(/ago/)).toBeNull();
    expect(screen.getByText(/2:21(:17)? pm/i)).toBeInTheDocument();
  });

  it('keeps an undated event rather than dropping it', () => {
    render(
      <EventTimeline
        events={[event(), event({ id: 'e2', title: 'Disqualified', at: null })]}
      />,
    );

    // Dropping it would make the record read as though it never happened.
    expect(screen.getByText('Disqualified')).toBeInTheDocument();
    expect(screen.getByText('Date not recorded')).toBeInTheDocument();
  });

  it('renders a marker in place of the dot when one is supplied', () => {
    render(
      <EventTimeline
        events={[event({ marker: <span data-testid="avatar">JP</span> })]}
      />,
    );

    expect(screen.getByTestId('avatar')).toBeInTheDocument();
  });

  it('states emptiness instead of drawing an empty rail', () => {
    render(<EventTimeline events={[]} emptyTitle="Nothing recorded yet" />);

    expect(screen.getByText('Nothing recorded yet')).toBeInTheDocument();
    expect(screen.queryByTestId('event-timeline')).toBeNull();
  });

  it('carries the detail and the tags of an event', () => {
    render(
      <EventTimeline
        events={[
          event({
            actor: 'Jayson Personal',
            detail: 'Outside my area',
            tags: <span>counts as work</span>,
          }),
        ]}
      />,
    );

    const timeline = screen.getByTestId('event-timeline');
    expect(within(timeline).getByText('Jayson Personal')).toBeInTheDocument();
    expect(within(timeline).getByText('Outside my area')).toBeInTheDocument();
    expect(within(timeline).getByText('counts as work')).toBeInTheDocument();
  });
});
