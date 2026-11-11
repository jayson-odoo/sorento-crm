/** TRACE-ENTITY-TOOL: Entity match, the named tool shown open, the span pass code label, Ran after / Next wording. */
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
    id: 'ZZT-turn-span-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.1',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-10-27T00:00:00Z',
    finished_at: '2026-10-27T00:00:02Z',
    trace: [],
    response: null,
    trace_detail,
  };
}


const SPAN_BASE = {
  rows_rendered: 0,
  near_exact_rows: 0,
  fallback: false,
  fallback_reason: null,
  provider: 'gemini',
  model: 'gem-y',
  model_source: 'global',
  ms: 800,
  tokens: { prompt_tokens: 40, completion_tokens: 3, total_tokens: 43, cached_tokens: 0 },
  matched_rows: [],
  near_exact: [],
  final_block: {},
};

function open(data: ChatbotTurnDetail) {
  turnState = { data, isLoading: false, isError: false };
  render(<TurnDetailDrawer turnId="ZZT-turn-span-1" onOpenChange={vi.fn()} />);
}

describe('TRACE-ENTITY-TOOL Entity match', () => {
  it('shows each typed word, its codes, the tier and the unplaced words', () => {
    open(
      detail({
        entity_match: {
          words: [
            { word: 'srtwc286', codes: ['SRTWC286'], more: 0, tiers: ['exact'], kinds: ['product'], ambiguous: false },
            {
              word: 'srtw',
              codes: Array.from({ length: 10 }, (_, i) => `SRTW${i}`),
              more: 4,
              tiers: ['prefix'],
              kinds: ['product'],
              ambiguous: false,
            },
          ],
          unplaced: ['zzq'],
          not_checked: [],
        },
      }),
    );
    const section = screen.getByTestId('entity-match');
    expect(section).toHaveTextContent('srtwc286');
    expect(section).toHaveTextContent('SRTWC286');
    expect(section).toHaveTextContent('exact');
    expect(section).toHaveTextContent('+4 more');
    expect(section).toHaveTextContent('starts with');
    expect(screen.getByTestId('entity-match-unplaced')).toHaveTextContent('zzq');
  });

  it('says so when the turn ran no code lookup', () => {
    open(detail({ entity_match: null }));
    fireEvent.click(screen.getByTestId('section-entity-match-trigger'));
    expect(screen.getByText('No code lookup this turn.')).toBeInTheDocument();
  });
});

describe('TRACE-ENTITY-TOOL Tool shown open', () => {
  it('shows the tool name and ms without opening the section', () => {
    open(
      detail({
        tool: { name: 'crm_inventory_stock_balance_list', args: {}, envelope: null, ms: 157 },
      }),
    );
    expect(screen.getByText('crm_inventory_stock_balance_list')).toBeInTheDocument();
    expect(screen.getByText('157')).toBeInTheDocument();
  });
});

describe('TRACE-ENTITY-TOOL span pass code label', () => {
  it('labels a product code span "sent to the code lookup", not skipped', () => {
    open(
      detail({
        span_extract: { ...SPAN_BASE, spans: [{ text: 'srtwc286', type: 'product_code', status: 'skipped', close: 0 }] },
      }),
    );
    fireEvent.click(screen.getByTestId('section-span-pass-trigger'));
    expect(screen.getByText('sent to the code lookup')).toBeInTheDocument();
    expect(screen.queryByText('skipped')).toBeNull();
  });
});

describe('TRACE-ENTITY-TOOL Ran after / Next wording', () => {
  it('says first message / no later message when the neighbours were looked up', () => {
    open(detail({ order: { ticket: 1, wait_ms: 10, previous: null, next: null, neighbours_checked: true } }));
    expect(screen.getByText('First message in this conversation')).toBeInTheDocument();
    expect(screen.getByText('No later message yet')).toBeInTheDocument();
  });

  it('keeps "Not recorded" when the neighbours were not looked up', () => {
    open(detail({ order: { ticket: 1, wait_ms: 10, previous: null, next: null, neighbours_checked: false } }));
    expect(screen.getAllByText('Not recorded on this turn.')).toHaveLength(2);
  });
});
