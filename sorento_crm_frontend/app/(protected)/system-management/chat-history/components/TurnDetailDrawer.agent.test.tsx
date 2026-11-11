/**
 * AGENT-PANEL-FIXES D: an agent turn's trace showed "Not recorded on this turn" in every section (owner, 11 Nov).
 * The drawer now shows an Agent section (rounds, thinking, tool calls, context sent to the AI) for an agent turn and
 * leaves out the bot pipeline's sections, which the agent never writes.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

import { TurnDetailDrawer } from './TurnDetailDrawer';
import type { ChatbotTurnDetail, TurnDetail, TurnDetailAgent } from '../types/chatbotTurn.types';

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

const PROJECT = '8a05b54a-aecb-4727-90e1-ce96506faf36';
const PAGE_NOTE = `The page the user has open, as quoted data of what is on their screen.\n{"title": "ZZT Tower", "path": "/project-sales/${PROJECT}"}`;

function agent(): TurnDetailAgent {
  return {
    rounds: [
      {
        n: 0, kind_of_call: 'dealer_access', model: 'zzt-model-1', ms: 600, prompt_tokens: 300, completion_tokens: 5,
        cached_tokens: 0, reasoning_tokens: null, stop: 'text', called: [], tools_offered: 0, tool_schema_chars: 0,
        message_chars: 527,
      },
      {
        n: 1, kind_of_call: 'round', model: 'zzt-model-1', ms: 4210, prompt_tokens: 26810, completion_tokens: 412,
        cached_tokens: 0, reasoning_tokens: 120, stop: 'tool_calls', called: ['crm_project_quotation_lines'],
        tools_offered: 53, tool_schema_chars: 93991, message_chars: 12852,
      },
      {
        n: 2, kind_of_call: 'round', model: 'zzt-model-1', ms: 3120, prompt_tokens: 5120, completion_tokens: 980,
        cached_tokens: 4096, reasoning_tokens: 60, stop: 'answer', called: ['answer'],
        tools_offered: 3, tool_schema_chars: 3362, message_chars: 16445,
      },
    ],
    reasoning: [{ round: 1, kind_of_call: 'round', text: 'Read the lines of both quotations first.' }],
    tools: [
      {
        name: 'crm_project_quotation_lines', args: { refs: ['PRJQ-2026-0007'], project_id: PROJECT }, status: 'ok', ms: 84,
        rows: 3,
        result_chars: 3431, more: 0, detail: null,
      },
    ],
    plan: [],
    context: {
      prompt_key: 'chatbot_agent', prompt_version: 14, system_chars: 6842, context_before: '',
      context_before_chars: 0, context_after: PAGE_NOTE, context_after_chars: PAGE_NOTE.length,
      history_messages: 4, history_summary: false, history_chars: 900, file_text_chars: 0, images: 0,
      tools: ['crm_project_quotation_lines', 'crm_query', 'answer'], tool_schema_chars: 93991,
    },
    failures: [],
    totals: { calls: 2, ms: 7330, prompt_tokens: 31930, completion_tokens: 1392, cached_tokens: 4096 },
  };
}

function detail(withAgent: TurnDetailAgent | null): TurnDetail {
  return {
    agent: withAgent,
    stages: [{ name: 'route', started_at: null, ms: 333, status: 'ok', summary: 'agent', error: null, facts: {} }],
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

function turn(trace_detail: TurnDetail): ChatbotTurnDetail {
  return {
    id: 'ZZT-turn-agent-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'panel-zzt-1',
    status: 'done',
    stage: 'sent',
    branch_kind: null,
    attempt: 1,
    is_test: false,
    created_at: '2026-11-11T08:00:00Z',
    finished_at: '2026-11-11T08:00:08Z',
    trace: [],
    response: null,
    trace_detail,
  };
}

function open(d: TurnDetail) {
  turnState = { data: turn(d), isLoading: false, isError: false };
  render(<TurnDetailDrawer turnId="ZZT-turn-agent-1" onOpenChange={() => {}} />);
}

describe('TurnDetailDrawer, an agent turn (AGENT-PANEL-FIXES D)', () => {
  it('shows each round with model, time, tokens in and out, and why it stopped', () => {
    open(detail(agent()));
    const rounds = screen.getByTestId('section-agent-rounds');
    expect(within(rounds).getAllByTestId('agent-round')).toHaveLength(3);
    const [side, first, second] = within(rounds).getAllByTestId('agent-round');
    expect(side).toHaveTextContent('Dealer access check');
    expect(side).not.toHaveTextContent('Round');
    expect(first).toHaveTextContent('Round 1');
    expect(second).toHaveTextContent('Round 2');
    expect(first).toHaveTextContent('zzt-model-1');
    expect(first).toHaveTextContent('4,210 ms');
    expect(first).toHaveTextContent('26,810 in');
    expect(first).toHaveTextContent('412 out');
    expect(first).toHaveTextContent('Called crm_project_quotation_lines');
    expect(first).toHaveTextContent('53 tools offered');
    expect(second).toHaveTextContent('Answered');
    expect(second).toHaveTextContent('4,096 cached');
    expect(rounds).toHaveTextContent('31,930 in');
  });

  it('shows the thinking and each tool call with arguments, rows, size, time and status', () => {
    open(detail(agent()));
    expect(screen.getByTestId('section-agent-thinking')).toHaveTextContent('Read the lines of both quotations first.');
    const tools = screen.getByTestId('section-agent-tools');
    expect(tools).toHaveTextContent('crm_project_quotation_lines');
    expect(tools).toHaveTextContent('3 rows');
    expect(tools).toHaveTextContent('3,431 chars');
    expect(tools).toHaveTextContent('84 ms');
    expect(tools).toHaveTextContent('ok');
    expect(tools).toHaveTextContent('PRJQ-2026-0007');
  });

  it('shows no UUID anywhere: id arguments are left out and ids in the page note read as [id]', () => {
    open(detail(agent()));
    expect(document.body.textContent).not.toContain(PROJECT);
    expect(screen.getByTestId('section-agent-tools')).not.toHaveTextContent('project_id');
    expect(screen.getByTestId('section-agent-context')).toHaveTextContent('/project-sales/[id]');
  });

  it('shows the context sent to the AI: prompt and version, the page note, history and the tool list', () => {
    open(detail(agent()));
    const ctx = screen.getByTestId('section-agent-context');
    expect(ctx).toHaveTextContent('chatbot_agent v14');
    expect(ctx).toHaveTextContent('4 messages');
    expect(ctx).toHaveTextContent('3 tools');
    expect(ctx).toHaveTextContent('ZZT Tower');
  });

  it('leaves out the bot pipeline sections, so nothing reads "Not recorded on this turn"', () => {
    open(detail(agent()));
    for (const id of ['section-parse', 'section-apply', 'section-memory', 'section-context', 'section-decay',
      'section-focus', 'section-tool', 'section-session', 'section-sent', 'section-order']) {
      expect(screen.queryByTestId(`${id}-trigger`)).toBeNull();
    }
    expect(screen.queryByText(/Not recorded on this turn/)).toBeNull();
    fireEvent.click(screen.getByTestId('section-stages-trigger'));
    expect(screen.getByTestId('section-stages')).toHaveTextContent('route');
  });

  it('keeps the bot pipeline sections for a bot turn', () => {
    open(detail(null));
    expect(screen.queryByTestId('section-agent-rounds')).toBeNull();
    expect(screen.getByTestId('section-parse-trigger')).toBeInTheDocument();
  });
});
