import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TraceView } from './TraceView';
import type { Trace, TraceSpan } from '../services/aiUsageService';

// Match PromptDetail/PromptsList style: mock the hook module directly so the
// component never touches react-query's network path. next/link renders fine
// in jsdom, so it is NOT stubbed (mirrors the prompts tests).
const useQueryTrace = vi.fn();
vi.mock('../hooks/useAIUsage', () => ({
  useQueryTrace: (messageId: string) => useQueryTrace(messageId),
}));

// jsdom has no scrollIntoView; guard in case any child ref calls it.
if (!(HTMLElement.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView) {
  (HTMLElement.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = () => {};
}

function makeSpan(partial: Partial<TraceSpan> & Pick<TraceSpan, 'id' | 'span_kind' | 'name'>): TraceSpan {
  return {
    parent_id: null,
    dotted_order: '000000',
    input_json: null,
    output_json: null,
    status: 'ok',
    error: null,
    latency_ms: 0,
    request_model: null,
    finish_reason: null,
    invocation_params: null,
    tokens_in: 0,
    tokens_out: 0,
    prompt_name: null,
    prompt_version: null,
    tool_name: null,
    tool_call_id: null,
    tool_args: null,
    tool_result: null,
    query: null,
    documents: null,
    top_k: null,
    ...partial,
  };
}

const ROOT_ID = 'span-agent-root';

function buildTrace(overrides: Partial<TraceSpan>[] = []): Trace {
  const root = makeSpan({
    id: ROOT_ID,
    parent_id: null,
    dotted_order: '000001',
    span_kind: 'AGENT',
    name: 'assistant turn',
    latency_ms: 400,
    input_json: { query: 'what is my stock' },
    output_json: { reply: 'here you go' },
  });
  const llm = makeSpan({
    id: 'span-llm',
    parent_id: ROOT_ID,
    dotted_order: '000002',
    span_kind: 'LLM',
    name: 'chat gpt-4o',
    latency_ms: 220,
    request_model: 'gpt-4o',
    tokens_in: 10,
    tokens_out: 5,
    prompt_name: 'agent_system',
    prompt_version: 1,
    input_json: { messages: [{ role: 'user', content: 'hi there' }] },
    output_json: { content: 'the model reply' },
    ...overrides[1],
  });
  const tool = makeSpan({
    id: 'span-tool',
    parent_id: ROOT_ID,
    dotted_order: '000003',
    span_kind: 'TOOL',
    name: 'crm_inventory_stock_balance_list',
    latency_ms: 90,
    tool_name: 'crm_inventory_stock_balance_list',
    tool_args: { product: 'widget' },
    tool_result: { rows: 3 },
  });
  const retriever = makeSpan({
    id: 'span-retriever',
    parent_id: ROOT_ID,
    dotted_order: '000004',
    span_kind: 'RETRIEVER',
    name: 'rag select',
    latency_ms: 30,
    query: 'stock of widget',
    documents: [{ id: 'd1', content: 'doc', score: 0.9 }],
    top_k: 5,
  });
  const spans = [root, llm, tool, retriever];
  return {
    id: 'trace-1',
    message_id: 'msg-1',
    conversation_id: 'conv-1',
    user_id: 'u-1',
    session_id: 's-1',
    status: 'ok',
    flagged: false,
    env: 'test',
    total_tokens_in: 10,
    total_tokens_out: 5,
    latency_ms: 400,
    span_count: spans.length,
    started_at: '2026-07-04T09:00:00',
    ended_at: '2026-07-04T09:00:00',
    created_at: '2026-07-04T09:00:00',
    spans,
  };
}

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TraceView messageId="msg-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useQueryTrace.mockReset();
});
afterEach(() => cleanup());

describe('TraceView', () => {
  it('renders the loading state', () => {
    useQueryTrace.mockReturnValue({ isLoading: true, isError: false, data: undefined });
    renderView();
    expect(screen.getByText(/Loading trace/i)).toBeInTheDocument();
  });

  it('renders the empty state when the trace is not found', () => {
    useQueryTrace.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error('No trace for this message'),
      data: undefined,
    });
    renderView();
    const empty = screen.getByTestId('trace-empty');
    expect(empty).toBeInTheDocument();
    expect(within(empty).getByText(/No trace for this turn/i)).toBeInTheDocument();
  });

  it('renders a generic error (not the empty state) for a non-404 failure', () => {
    useQueryTrace.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error('boom the server exploded'),
      data: undefined,
    });
    renderView();
    const empty = screen.getByTestId('trace-empty');
    expect(within(empty).getByText(/Could not load trace/i)).toBeInTheDocument();
    expect(within(empty).getByText(/boom the server exploded/i)).toBeInTheDocument();
  });

  it('renders the waterfall with one row per span', () => {
    useQueryTrace.mockReturnValue({ isLoading: false, isError: false, data: buildTrace() });
    renderView();
    expect(screen.getByTestId('trace-waterfall')).toBeInTheDocument();
    expect(screen.getAllByTestId('trace-span-row')).toHaveLength(4);
    // token badge shows on the LLM row only (10 in + 5 out).
    expect(screen.getByText('15 tok')).toBeInTheDocument();
  });

  it('shows the inspector with input/output and the prompt link when an LLM row is clicked', () => {
    useQueryTrace.mockReturnValue({ isLoading: false, isError: false, data: buildTrace() });
    renderView();

    fireEvent.click(screen.getByText('chat gpt-4o'));

    const inspector = screen.getByTestId('trace-inspector');
    expect(within(inspector).getByText(/hi there/)).toBeInTheDocument();
    expect(within(inspector).getByText(/the model reply/)).toBeInTheDocument();

    const link = screen.getByTestId('trace-prompt-link');
    expect(link).toHaveAttribute('href', '/system-management/ai-assistant/prompts/agent_system');
    expect(link).toHaveTextContent('agent_system@v1');
  });

  it('renders "(fallback)" when the LLM span has a null prompt_version', () => {
    useQueryTrace.mockReturnValue({
      isLoading: false,
      isError: false,
      data: buildTrace([undefined as never, { prompt_version: null }]),
    });
    renderView();

    fireEvent.click(screen.getByText('chat gpt-4o'));
    const link = screen.getByTestId('trace-prompt-link');
    expect(link).toHaveTextContent('agent_system (fallback)');
    expect(link).not.toHaveTextContent('@v');
  });

  it('hides a kind\'s rows via the Filter kinds toggle', () => {
    useQueryTrace.mockReturnValue({ isLoading: false, isError: false, data: buildTrace() });
    renderView();
    expect(screen.getAllByTestId('trace-span-row')).toHaveLength(4);

    // open the filter panel
    fireEvent.click(screen.getByRole('button', { name: 'Filter kinds' }));
    // toggle the TOOL chip off (exact name match hits the chip, not the row button)
    fireEvent.click(screen.getByRole('button', { name: 'TOOL' }));

    const rows = screen.getAllByTestId('trace-span-row');
    expect(rows).toHaveLength(3);
    expect(screen.queryByText('crm_inventory_stock_balance_list')).not.toBeInTheDocument();
  });
});
