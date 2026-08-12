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
