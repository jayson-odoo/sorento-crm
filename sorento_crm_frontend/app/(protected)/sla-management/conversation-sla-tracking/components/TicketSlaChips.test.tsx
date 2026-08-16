import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import TicketSlaChips from './TicketSlaChips';

const inMinutes = (m: number) => new Date(Date.now() + m * 60_000).toISOString();

describe('TicketSlaChips', () => {
  it('fresh: shows a respond countdown and a resolve countdown, no responded/escalated markers', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(46)}
        dueAtResolution={inMinutes(350)}
        isResponded={false}
        currentTier={1}
        escalatedAt={null}
      />,
    );
    expect(screen.getByText(/Respond in/i)).toBeInTheDocument();
    expect(screen.getByText(/Resolve in/i)).toBeInTheDocument();
    expect(screen.getByText('Tier 1')).toBeInTheDocument();
    expect(screen.queryByText('Responded')).not.toBeInTheDocument();
    expect(screen.queryByText('Escalated')).not.toBeInTheDocument();
    expect(screen.queryByText(/Response breached/i)).not.toBeInTheDocument();
  });

  it('overdue (unresponded, past due): shows an overdue respond chip + breach warning', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(-22)}
        dueAtResolution={inMinutes(120)}
        isResponded={false}
        currentTier={2}
        escalatedAt={inMinutes(-20)}
      />,
    );
    expect(screen.getByText(/Respond .*overdue/i)).toBeInTheDocument();
    expect(screen.getByText(/Response breached/i)).toBeInTheDocument();
    expect(screen.getByText('Escalated')).toBeInTheDocument();
  });

  it('responded (only the resolution clock races): shows a Responded chip, no respond countdown', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(-150)}
        dueAtResolution={inMinutes(92)}
        isResponded
        respondedAt={inMinutes(-90)}
        currentTier={1}
        escalatedAt={null}
      />,
    );
    expect(screen.getByText('Responded')).toBeInTheDocument();
    expect(screen.queryByText(/^Respond /i)).not.toBeInTheDocument();
    expect(screen.getByText(/Resolve in/i)).toBeInTheDocument();
    expect(screen.queryByText(/Response breached/i)).not.toBeInTheDocument();
  });

  // ---- Urgency (feedback 2026-08-16, item 6a) ----------------------------
  // Three steps, not two: red already said "too late", and the amber step is
  // what gives an extended deadline a chance to be seen before it breaches.
  it('plenty of time left: the resolve chip stays neutral', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(600)}
        dueAtResolution={inMinutes(2880)}
        isResponded
        currentTier={1}
      />,
    );
    const chip = screen.getByText(/Resolve in/i);
    expect(chip.className).not.toMatch(/amber/);
    expect(chip.className).not.toMatch(/destructive/);
  });

  it('under four hours left: the resolve chip turns amber', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(600)}
        dueAtResolution={inMinutes(90)}
        isResponded
        currentTier={1}
      />,
    );
    expect(screen.getByText(/Resolve in/i).className).toMatch(/amber/);
  });

  it('past due: the resolve chip turns red', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(600)}
        dueAtResolution={inMinutes(-5)}
        isResponded
        currentTier={1}
      />,
    );
    expect(screen.getByText(/Resolve .*overdue/i).className).toMatch(/destructive/);
  });

  // ---- Extended marker (feedback 2026-08-16, item 6b) --------------------
  it('an extended deadline says so, carrying the new due date', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(600)}
        dueAtResolution={inMinutes(2880)}
        isResponded
        currentTier={1}
        extensionCount={1}
      />,
    );
    const chip = screen.getByTestId('sla-extended-chip');
    expect(chip).toHaveTextContent('Extended');
    expect(chip.getAttribute('title')).toMatch(/^Deadline extended to /);
  });

  it('counts repeat extensions', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(600)}
        dueAtResolution={inMinutes(2880)}
        isResponded
        currentTier={1}
        extensionCount={3}
      />,
    );
    expect(screen.getByTestId('sla-extended-chip')).toHaveTextContent('Extended ×3');
  });

  it('a never-extended row carries no marker', () => {
    render(
      <TicketSlaChips
        dueAt={inMinutes(600)}
        dueAtResolution={inMinutes(2880)}
        isResponded
        currentTier={1}
        extensionCount={0}
      />,
    );
    expect(screen.queryByTestId('sla-extended-chip')).not.toBeInTheDocument();
  });

  it('no deadlines set: renders "not set" placeholders instead of crashing', () => {
    render(
      <TicketSlaChips
        dueAt={null}
        dueAtResolution={null}
        isResponded={false}
        currentTier={1}
        escalatedAt={null}
      />,
    );
    expect(screen.getByText(/Respond not set/i)).toBeInTheDocument();
    expect(screen.getByText(/Resolve not set/i)).toBeInTheDocument();
  });
});
