/** ENTITY-EXTRACT-MATCH S3 (AC-S3-6): the Span pass section shows a phrase's meaning and which form matched, and the
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

describe('TurnDetailDrawer span meaning (AC-S3-6)', () => {
  it('shows the meaning of a phrase and that the meaning matched', () => {
    const body = open({
      ...BASE,
      embedding_model: 'gemini-embedding-001',
      spans: [
        {
          text: 'zzemas',
          type: 'spec_value',
          meaning: 'zz gold',
          matched_by: 'meaning',
          status: 'resolved',
          close: 1,
          candidates: [{ list: 'spec', label: 'Finish or colour ZZ gold', score: 0.91, signal: 'partial' }],
        },
      ],
    });
    expect(body).toHaveTextContent('zzemas');
    expect(screen.getByTestId('span-meaning')).toHaveTextContent('zz gold');
    expect(screen.getByTestId('span-matched-by')).toHaveTextContent('meaning');
  });

  it('shows that the text matched when the meaning did not, and nothing when the phrase has no meaning', () => {
    const body = open({
      ...BASE,
      embedding_model: 'gemini-embedding-001',
      spans: [
        { text: 'zzkimlan', type: 'customer', meaning: 'zz nonsense', matched_by: 'text', status: 'resolved', close: 1 },
        { text: 'zzplain', type: 'brand', meaning: null, matched_by: 'text', status: 'resolved', close: 1 },
      ],
    });
    const meanings = screen.getAllByTestId('span-meaning');
    expect(meanings).toHaveLength(1);
    expect(meanings[0]).toHaveTextContent('zz nonsense');
    expect(screen.getAllByTestId('span-matched-by')[0]).toHaveTextContent('text');
    expect(body).toHaveTextContent('zzplain');
  });

  it('names the embedding model on the call line', () => {
    open({ ...BASE, embedding_model: 'gemini-embedding-001', spans: [] });
    expect(screen.getByTestId('span-pass-call')).toHaveTextContent('gemini-embedding-001');
  });

  it('an older event without the new fields still renders', () => {
    const body = open({ ...BASE, spans: [{ text: 'zzold', type: 'brand', status: 'resolved', close: 1 }] });
    expect(body).toHaveTextContent('zzold');
    expect(screen.queryByTestId('span-meaning')).toBeNull();
  });
});
