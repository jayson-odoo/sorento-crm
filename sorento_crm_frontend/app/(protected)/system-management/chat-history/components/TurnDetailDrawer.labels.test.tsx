/**
 * N7 (reviewer finding, PR #1304): the Memory section rendered raw backend codes
 * verbatim - "full" for the context level, "usual_products (tallied)" for a saved
 * fact - instead of the human labels the rest of the chatbot memory screens already
 * use (`ContactChatbotSection.tsx`'s own `LEVEL_LABEL` / `SOURCE_BADGE`).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

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
    id: 'ZZT-turn-labels-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.1',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-09-27T00:00:00Z',
    finished_at: '2026-09-27T00:00:02Z',
    trace: [],
    response: null,
    trace_detail,
  };
}

describe('TurnDetailDrawer Memory section - human labels, not raw codes (N7)', () => {
  it('shows "Full memory", never the raw "full" level code', () => {
    const detail = emptyDetail();
    detail.memory = {
      level: { own: 'full', effective: 'full' },
      focus: { before: null, after: {}, writer: null },
      profile: { before: {}, after: {}, writer: null },
      episodes: { read: [], written: null, writer: 'none' },
      facts_saved: [],
    };
    turnState = { data: detailTurn(detail), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-labels-1" onOpenChange={vi.fn()} />);

    fireEvent.click(screen.getByTestId('section-memory-trigger'));
    const panel = screen.getByTestId('section-memory');

    expect(within(panel).getByText('Full memory')).toBeInTheDocument();
    expect(within(panel).queryByText('full')).not.toBeInTheDocument();
  });

  it('shows "Usual products (Learned)", never the raw "usual_products (tallied)" code', () => {
    const detail = emptyDetail();
    detail.memory = {
      level: { own: null, effective: 'off' },
      focus: { before: null, after: {}, writer: null },
      profile: { before: {}, after: {}, writer: null },
      episodes: { read: [], written: null, writer: 'none' },
      facts_saved: [{ key: 'usual_products', source: 'tallied' }],
    };
    turnState = { data: detailTurn(detail), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-labels-1" onOpenChange={vi.fn()} />);

    fireEvent.click(screen.getByTestId('section-memory-trigger'));
    const panel = screen.getByTestId('section-memory');

    expect(within(panel).getByText(/Usual products \(Learned\)/)).toBeInTheDocument();
    expect(within(panel).queryByText(/usual_products \(tallied\)/)).not.toBeInTheDocument();
  });
});
