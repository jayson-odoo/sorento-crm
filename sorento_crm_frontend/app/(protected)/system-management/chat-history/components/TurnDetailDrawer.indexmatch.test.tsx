/** CHAT-INDEX-VIZ FE-1: the drawer renders an "Index match" section right after Parse. */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

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

function detail(extra: Partial<TurnDetail>): ChatbotTurnDetail {
  const trace_detail: TurnDetail = {
    stages: [],
    parse: null,
    decay: [],
    open_question: null,
    focus: [],
    tool: null,
    crossdomain: [],
    reveals: { restricted_fields_seen: [], granted: [], dropped: [] },
    session: { before: {}, after: {}, diff: [] },
    ...extra,
  };
  return {
    id: 'ZZT-turn-idx-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.1',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-10-21T00:00:00Z',
    finished_at: '2026-10-21T00:00:02Z',
    trace: [],
    response: null,
    trace_detail,
  };
}

describe('TurnDetailDrawer Index match section', () => {
  it('is present and shows the empty text for a turn that sent the full lists', () => {
    turnState = { data: detail({ index_match: null }), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-idx-1" onOpenChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId('section-index-match-trigger'));
    expect(screen.getByTestId('section-index-match')).toHaveTextContent(
      'No list matching was recorded on this turn.',
    );
  });

  it('sits right after Parse and renders a row for a matched word', () => {
    turnState = {
      data: detail({
        index_match: {
          words: [{ text: 'frg', matched: true }],
          rows: [
            {
              word: 'frg',
              matched: [{ list: 'Specifications', entry: 'spec finish = french_gold (French Gold)', close_spelling: false }],
              parser_got: ['- "frg": spec finish = french_gold (French Gold)'],
              understood: [{ text: '"frg" as a specification: finish = french_gold' }],
              result: [{ outcome: 'kept', text: 'Kept' }],
            },
          ],
          held: [],
          not_from_lists: [],
          failed: false,
        },
      }),
      isLoading: false,
      isError: false,
    };
    render(<TurnDetailDrawer turnId="ZZT-turn-idx-1" onOpenChange={vi.fn()} />);
    const parse = screen.getByTestId('section-parse');
    const index = screen.getByTestId('section-index-match');
    expect(parse.compareDocumentPosition(index) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByTestId('section-index-match-trigger'));
    expect(screen.getByTestId('index-row-frg')).toBeInTheDocument();
  });
});
