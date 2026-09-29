/**
 * S12 (reviewer finding, PR #1304): a queue TIMEOUT sends `wait_ms: null` (it never
 * finished waiting - `app/services/chatbot/trace_detail.py::_order`, "no `wait_ms`,
 * since it never finished waiting"). The drawer used to divide `null / 1000`, which
 * rendered "Waited NaN s"... actually "Waited 0.0 s" once `null` coerced through
 * `.toFixed`, silently hiding the timeout. The mockup's timed-out wording (AC-MEM015,
 * `chatbot-memory-27sep-mockup-ticket.html`: "Timed out ... waited 45 s for #13,
 * which never finished") names the ticket it waited for - the PREVIOUS turn's own
 * ticket, off `order.previous`.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';

import { TurnDetailDrawer } from './TurnDetailDrawer';
import type { ChatbotTurnDetail, TurnDetail } from '../types/chatbotTurn.types';

let turnState: { data: ChatbotTurnDetail | undefined; isLoading: boolean; isError: boolean } = {
  data: undefined,
  isLoading: false,
  isError: false,
};

vi.mock('../hooks/useChatbotTurns', () => ({
  useChatbotTurn: () => turnState,
}));

afterEach(() => {
  cleanup();
  turnState = { data: undefined, isLoading: false, isError: false };
});

function emptyDetail(): TurnDetail {
  return {
    stages: [],
    parse: null,
    decay: [],
    open_question: null,
    focus: [],
    tool: null,
    crossdomain: [],
    reveals: { restricted_fields_seen: [], granted: [], dropped: [] },
    session: { before: {}, after: {}, diff: [] },
  };
}

function detailTurn(trace_detail: TurnDetail): ChatbotTurnDetail {
  return {
    id: 'ZZT-turn-order-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.1',
    status: 'failed',
    stage: 'queued',
    branch_kind: null,
    attempt: 1,
    is_test: false,
    created_at: '2026-09-27T00:00:00Z',
    finished_at: '2026-09-27T00:00:45Z',
    trace: [],
    response: null,
    trace_detail,
  };
}

describe('TurnDetailDrawer Order section - a queue timeout (S12, AC-MEM015)', () => {
  it('names the ticket it timed out waiting for instead of rendering "Waited 0.0 s"', () => {
    const detail = emptyDetail();
    detail.order = {
      ticket: 14,
      wait_ms: null,
      previous: {
        turn_id: 'ZZT-turn-13',
        created_at: '2026-09-27T00:00:00Z',
        message: 'stock SRTWB1455',
        ticket: 13,
      },
      next: null,
    };
    turnState = { data: detailTurn(detail), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-order-1" onOpenChange={vi.fn()} />);

    // "Order" opens by default (`Section title="Order" ... defaultOpen`).
    const panel = screen.getByTestId('section-order');

    expect(within(panel).queryByText('0.0 s')).not.toBeInTheDocument();
    expect(within(panel).getByText(/timed out/i)).toBeInTheDocument();
    expect(within(panel).getByText(/waited for #13/i)).toBeInTheDocument();
  });

  it('still renders the plain waited seconds when the turn actually finished waiting', () => {
    const detail = emptyDetail();
    detail.order = { ticket: 14, wait_ms: 400, previous: null, next: null };
    turnState = { data: detailTurn(detail), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-order-1" onOpenChange={vi.fn()} />);

    const panel = screen.getByTestId('section-order');

    expect(within(panel).getByText('0.4 s')).toBeInTheDocument();
  });
});
