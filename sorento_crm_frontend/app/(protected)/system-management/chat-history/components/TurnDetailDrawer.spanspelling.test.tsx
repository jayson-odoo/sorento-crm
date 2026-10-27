/** (#1898 nit) a spelling-only turn says so. Base: ENTITY-EXTRACT-MATCH S3 (AC-S3-6): the Span pass section shows a phrase's meaning and which form matched, and the
 * call line names the embedding model. Assumed event fields: spans[].meaning (string | null), spans[].matched_by
 * ('meaning' | 'text' | null) and span_extract.embedding_model (string | null). */
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

function detail(spanExtract: Record<string, unknown>): ChatbotTurnDetail {
  const trace_detail = {
    stages: [],
    parse: null,
    decay: [],
    open_question: null,
    focus: [],
    tool: null,
    crossdomain: [],
    reveals: { restricted_fields_seen: [], granted: [], dropped: [] },
    session: { before: {}, after: {}, diff: [] },
    span_extract: spanExtract,
  } as unknown as TurnDetail;
  return {
    id: 'ZZT-turn-meaning-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.2',
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

const BASE = {
  rows_rendered: 1,
  near_exact_rows: 0,
  fallback: false,
  fallback_reason: null,
  provider: 'gemini',
  model: 'gem-y',
  model_source: 'label',
  ms: 90,
  tokens: { prompt_tokens: 5, completion_tokens: 2, total_tokens: 7, cached_tokens: 0 },
  matched_rows: [],
  near_exact: [],
  final_block: {},
};

function open(spanExtract: Record<string, unknown>) {
  turnState = { data: detail(spanExtract), isLoading: false, isError: false };
  render(<TurnDetailDrawer turnId="ZZT-turn-meaning-1" onOpenChange={vi.fn()} />);
  fireEvent.click(screen.getByTestId('section-span-pass-trigger'));
  return screen.getByTestId('section-span-pass');
}

describe('TurnDetailDrawer spelling-only turn', () => {
  it('says spelling only when no embedding model was used', () => {
    open({ ...BASE, embedding_model: null, spans: [] });
    expect(screen.getByTestId('span-pass-call')).toHaveTextContent('spelling only');
  });

  it('does not say it when a model was used', () => {
    open({ ...BASE, embedding_model: 'gemini-embedding-001', spans: [] });
    expect(screen.getByTestId('span-pass-call')).not.toHaveTextContent('spelling only');
  });
});
