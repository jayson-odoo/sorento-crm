/**
 * S2b Phase 2 test-first (AC-255, drawer half). `ChatTranscript`'s `failedTurnsOnly`
 * prop already ships from Phase 1 (`ChatThreadDrawer`'s "Failed turns only" toggle), so
 * this is a regression lock, not a red-then-green pair on its own - the genuinely new
 * Phase 2 surface for AC-255 is the LIST-level filter (the Chat History page's contact
 * rows, driven by a `failed-contacts` summary), covered separately in
 * `ChatbotFailedContactsFilter.test.tsx`, which IS red today.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import { ChatTranscript } from './ChatTranscript';
import type { ChatMessageRow } from '../types/chatHistory.types';
import type { ChatbotTurn } from '../types/chatbotTurn.types';

vi.mock('./TurnPanel', () => ({
  TurnPanel: ({ turn }: { turn: ChatbotTurn }) => <div data-testid="turn-panel">{turn.status}</div>,
}));
vi.mock('./StateTracePanel', () => ({ StateTracePanel: () => null }));

afterEach(() => cleanup());

function message(over: Partial<ChatMessageRow>): ChatMessageRow {
  return {
    id: 1,
    contact_id: 'ZZT-contact',
    type: 'incoming',
    message: 'hello',
    sent_at: '2026-09-05T06:00:00.000Z',
    latency_seconds: null,
    delivery_status: null,
    message_id: null,
    turn_id: null,
    state_trace: null,
    ...over,
  } as ChatMessageRow;
}

function turn(over: Partial<ChatbotTurn>): ChatbotTurn {
  return {
    id: 'ZZT-turn',
    contact_respond_id: 'ZZT-contact',
    message_id: null,
    status: 'done',
    stage: null,
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-09-05T06:00:00.000Z',
    finished_at: '2026-09-05T06:00:04.000Z',
    trace: [],
    response: null,
    ...over,
  };
}

describe('ChatTranscript failedTurnsOnly (AC-255)', () => {
  it('hides an incoming message whose turn answered fine when the filter is on', () => {
    const okMessage = message({ id: 1, message_id: 'wamid.ok', message: 'do you have stock' });
    const failedMessage = message({ id: 2, message_id: 'wamid.failed', message: 'still there?' });
    const byMessageId = new Map<string, ChatbotTurn>([
      ['wamid.ok', turn({ id: 'ok', message_id: 'wamid.ok', status: 'done' })],
      ['wamid.failed', turn({ id: 'failed', message_id: 'wamid.failed', status: 'failed' })],
    ]);

    render(
      <ChatTranscript
        messages={[okMessage, failedMessage]}
        turnsByMessageId={byMessageId}
        failedTurnsOnly
      />,
    );

    expect(screen.queryByText('do you have stock')).not.toBeInTheDocument();
    expect(screen.getByText('still there?')).toBeInTheDocument();
    expect(screen.getAllByTestId('turn-panel')).toHaveLength(1);
  });

  it('shows every message when the filter is off, regardless of turn status', () => {
    const okMessage = message({ id: 1, message_id: 'wamid.ok' });
    const failedMessage = message({ id: 2, message_id: 'wamid.failed' });
    const byMessageId = new Map<string, ChatbotTurn>([
      ['wamid.ok', turn({ id: 'ok', message_id: 'wamid.ok', status: 'done' })],
      ['wamid.failed', turn({ id: 'failed', message_id: 'wamid.failed', status: 'failed' })],
    ]);

    render(
      <ChatTranscript
        messages={[okMessage, failedMessage]}
        turnsByMessageId={byMessageId}
        failedTurnsOnly={false}
      />,
    );

    expect(screen.getAllByTestId('turn-panel')).toHaveLength(2);
  });

  it('shows an explanatory empty state when the filter is on and nothing failed', () => {
    const okMessage = message({ id: 1, message_id: 'wamid.ok' });
    const byMessageId = new Map<string, ChatbotTurn>([
      ['wamid.ok', turn({ id: 'ok', message_id: 'wamid.ok', status: 'done' })],
    ]);

    render(
      <ChatTranscript messages={[okMessage]} turnsByMessageId={byMessageId} failedTurnsOnly />,
    );

    expect(screen.getByText('No failed turns in this conversation.')).toBeInTheDocument();
  });
});
