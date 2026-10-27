/** ENTITY-EXTRACT-MATCH S2 fix: the prompt text reads from the top level; the Span pass section shows only with an event. */
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

const APPLY = { verdict: null, state_diff: null, narrowing: [], plan: null };

describe('TurnDetailDrawer prompt text', () => {
  it('renders the collapsible from the top-level prompt_text', () => {
    turnState = {
      data: detail({ apply: APPLY, prompt_text: 'ZZT rendered user block' }),
      isLoading: false,
      isError: false,
    };
    render(<TurnDetailDrawer turnId="ZZT-turn-span-1" onOpenChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId('section-apply-trigger'));
    fireEvent.click(screen.getByText('Prompt text sent to the parser'));
    expect(screen.getByText(/ZZT rendered user block/)).toBeInTheDocument();
  });

  it('shows no collapsible when prompt_text is null', () => {
    turnState = { data: detail({ apply: APPLY, prompt_text: null }), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-span-1" onOpenChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId('section-apply-trigger'));
    expect(screen.queryByText('Prompt text sent to the parser')).toBeNull();
  });
});

describe('TurnDetailDrawer Span pass section', () => {
  it('renders the phrases, the rows shown and no fallback line', () => {
    turnState = {
      data: detail({
        span_extract: {
          spans: [
            { text: 'frg', type: 'spec', status: 'close', close: 2, residual: true },
            { text: 'ZZT brand', type: 'brand', status: 'exact', close: 1, residual: false },
          ],
          rows_rendered: 3,
          near_exact_rows: 1,
          fallback: false,
          fallback_reason: null,
          provider: 'openai',
          model: 'gpt-x',
          model_source: 'label',
          ms: 120,
          matched_rows: ['Finish: French Gold'],
        },
      }),
      isLoading: false,
      isError: false,
    };
    render(<TurnDetailDrawer turnId="ZZT-turn-span-1" onOpenChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId('section-span-pass-trigger'));
    const body = screen.getByTestId('section-span-pass');
    expect(body).toHaveTextContent('frg');
    expect(body).toHaveTextContent('ZZT brand');
    expect(body).toHaveTextContent('residual');
    expect(body).toHaveTextContent('Finish: French Gold');
    expect(body).not.toHaveTextContent('fell back');
  });

  it('shows the fallback line with its reason', () => {
    turnState = {
      data: detail({
        span_extract: {
          spans: [],
          rows_rendered: 0,
          near_exact_rows: 0,
          fallback: true,
          fallback_reason: 'unreadable',
          provider: null,
          model: null,
          model_source: null,
          ms: 0,
          matched_rows: [],
        },
      }),
      isLoading: false,
      isError: false,
    };
    render(<TurnDetailDrawer turnId="ZZT-turn-span-1" onOpenChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId('section-span-pass-trigger'));
    expect(screen.getByTestId('section-span-pass')).toHaveTextContent('fell back');
    expect(screen.getByTestId('section-span-pass')).toHaveTextContent('unreadable');
  });

  it('is absent when the turn has no span event', () => {
    turnState = { data: detail({ span_extract: null }), isLoading: false, isError: false };
    render(<TurnDetailDrawer turnId="ZZT-turn-span-1" onOpenChange={vi.fn()} />);
    expect(screen.queryByTestId('section-span-pass-trigger')).toBeNull();
  });
});
