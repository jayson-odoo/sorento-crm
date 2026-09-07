/**
 * Chatbot growth r1, Slice D2 (AC-972, AC-973). Phase 2 test-first.
 */
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

function fullDetail(): TurnDetail {
  return {
    stages: [
      {
        name: 'received',
        started_at: '2026-09-07T00:00:00Z',
        ms: 3,
        status: 'ok',
        summary: 'Received the message.',
        error: null,
      },
      {
        name: 'understood',
        started_at: '2026-09-07T00:00:01Z',
        ms: 5,
        status: 'ok',
        summary: 'Understood as a business query.',
        error: null,
      },
    ],
    parse: {
      raw: { domain_hint: 'master_products' },
      post_processed: { domain_hint: 'master_products', entities: [] },
      prompt_version: 3,
      model: 'gpt-test',
    },
    decay: [
      {
        slot: 'products',
        value: 'SRTWC8517',
        set_at_turn: 1,
        age_turns: 4,
        age_minutes: 12,
        reason: 'ttl_exceeded',
      },
    ],
    open_question: {
      before: { kind: 'product_pick' },
      answer: { picks: [1] },
      after: null,
      handler: 'product_pick',
      outcome: 'focus.products set',
    },
    focus: [
      {
        slot: 'domain',
        before: 'master_products',
        after: 'incoming',
        rule: 'domain_from_switch_word',
        source: 'current_message',
      },
    ],
    tool: {
      name: 'crm_master_products_list',
      args: { product_ids: ['p-1'] },
      envelope: { items: [] },
      ms: 42,
    },
    crossdomain: [
      { rung: 1, tool: 'crm_incoming_stock_list', args: {}, rows: 2, rendered: true },
    ],
    reveals: {
      restricted_fields_seen: ['inventory.sellable'],
      granted: [],
      dropped: ['inventory.sellable'],
    },
    session: {
      before: { domain_hint: 'master_products' },
      after: { domain_hint: 'master_products', new_key: 'x' },
      diff: [{ key: 'new_key', change: 'gained' }],
    },
  };
}

function emptyDetail(): TurnDetail {
  return {
    stages: [
      {
        name: 'received',
        started_at: '2026-09-07T00:00:00Z',
        ms: 3,
        status: 'ok',
        summary: 'Received the message.',
        error: null,
      },
    ],
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
    id: 'ZZT-turn-detail-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.1',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-09-07T00:00:00Z',
    finished_at: '2026-09-07T00:00:02Z',
    trace: [],
    response: null,
    trace_detail,
  };
}

function openAllSections() {
  for (const testId of [
    'section-parse-trigger',
    'section-decay-trigger',
    'section-open-question-trigger',
    'section-focus-trigger',
    'section-tool-trigger',
    'section-crossdomain-trigger',
    'section-reveals-trigger',
    'section-session-trigger',
  ]) {
    fireEvent.click(screen.getByTestId(testId));
  }
}

describe('TurnDetailDrawer', () => {
  it('renders every section from a fixture carrying all kinds', () => {
    turnState = { data: detailTurn(fullDetail()), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-detail-1" onOpenChange={vi.fn()} />);

    openAllSections();

    expect(screen.getByText('received')).toBeInTheDocument();
    expect(screen.getByText('understood')).toBeInTheDocument();
    expect(screen.getByText('gpt-test')).toBeInTheDocument();
    expect(screen.getByText('ttl_exceeded')).toBeInTheDocument();
    expect(screen.getByText('product_pick')).toBeInTheDocument();
    expect(screen.getByText('domain_from_switch_word')).toBeInTheDocument();
    expect(screen.getByText('crm_master_products_list')).toBeInTheDocument();
    expect(screen.getByText('crm_incoming_stock_list')).toBeInTheDocument();
    expect(screen.getAllByText('inventory.sellable').length).toBeGreaterThan(0);
    expect(screen.getByText('new_key')).toBeInTheDocument();
  });

  it('renders an empty section for every kind absent from the trace', () => {
    turnState = { data: detailTurn(emptyDetail()), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-detail-1" onOpenChange={vi.fn()} />);

    openAllSections();

    expect(screen.getByText('No parse recorded.')).toBeInTheDocument();
    expect(screen.getByText('Nothing decayed this turn.')).toBeInTheDocument();
    expect(screen.getByText('No open question this turn.')).toBeInTheDocument();
    expect(screen.getByText('No focus rule fired this turn.')).toBeInTheDocument();
    expect(screen.getByText('No tool call recorded.')).toBeInTheDocument();
    expect(screen.getByText('No cross-domain probe this turn.')).toBeInTheDocument();
    expect(screen.getByText('No restricted field was on this answer.')).toBeInTheDocument();
  });

  it('a failed turn shows the failing stage first', () => {
    const detail = emptyDetail();
    detail.stages = [
      { name: 'understood', started_at: null, ms: 5, status: 'failed', summary: null, error: 'boom' },
      { name: 'received', started_at: null, ms: 3, status: 'ok', summary: 'ok', error: null },
    ];
    turnState = { data: detailTurn(detail), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-detail-1" onOpenChange={vi.fn()} />);

    const badges = screen.getAllByText(/received|understood/);
    expect(badges[0]).toHaveTextContent('understood');
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('renders nothing when no turn is picked', () => {
    turnState = { data: undefined, isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId={null} onOpenChange={vi.fn()} />);
    expect(screen.queryByTestId('section-stages')).not.toBeInTheDocument();
  });
});
