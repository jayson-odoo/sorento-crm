/**
 * The chatbot console transcript and the contact page's Chat history (#1317,
 * owner answer 3). Both are read-only: there is no message box to reply from,
 * so the shared bubble menu offers Copy only and a swipe moves nothing. Our
 * own "> quote" replies render as the same compact quoted block the other
 * thread surfaces show, never as a raw ">" line.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';

import { bubbleOf, openBubbleMenu, swipeRight } from '@/test-utils/replyGestures';
import { ChatTranscript } from './ChatTranscript';
import type { ChatMessageRow } from '../types/chatHistory.types';

vi.mock('./TurnPanel', () => ({ TurnPanel: () => null }));
vi.mock('./StateTracePanel', () => ({ StateTracePanel: () => null }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

afterEach(() => cleanup());
beforeEach(() => vi.clearAllMocks());

function message(over: Partial<ChatMessageRow>): ChatMessageRow {
  return {
    id: 1,
    contact_id: 'ZZT-contact',
    type: 'incoming',
    message: 'Is the sink in stock?',
    sent_at: '2026-09-05T06:00:00.000Z',
    latency_seconds: null,
    delivery_status: null,
    message_id: null,
    turn_id: null,
    state_trace: null,
    ...over,
  } as ChatMessageRow;
}

describe('ChatTranscript bubble menu (#1317)', () => {
  it('right click offers Copy only (no message box here), and Copy copies', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<ChatTranscript messages={[message({})]} />);
    expect(await openBubbleMenu('Is the sink in stock?')).toEqual(['Copy']);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('Is the sink in stock?'));
  });

  it('carries the hover chevron like every other thread surface', () => {
    render(<ChatTranscript messages={[message({})]} />);
    expect(
      within(bubbleOf('Is the sink in stock?')).getByRole('button', { name: 'Message actions' }),
    ).toBeInTheDocument();
  });

  it('a swipe does not move a bubble that has nothing to reply with', () => {
    render(<ChatTranscript messages={[message({})]} />);
    swipeRight('Is the sink in stock?');
    expect(bubbleOf('Is the sink in stock?').style.transform).toBe('');
  });

  it('an outgoing "> quote" reply renders as the compact quoted block, never raw', () => {
    render(
      <ChatTranscript
        messages={[
          message({ id: 1 }),
          message({
            id: 2,
            type: 'outgoing',
            message: '> Is the sink in stock?\nYes, 3 units.',
          }),
        ]}
      />,
    );
    const bubble = bubbleOf('Yes, 3 units.');
    const quote = within(bubble).getByTestId('quoted-context');
    expect(quote).toHaveTextContent('Is the sink in stock?');
    expect(within(quote).getByText('Is the sink in stock?')).toHaveClass('line-clamp-2');
    expect(bubble.textContent).not.toContain('> Is the sink');
  });

  it('an incoming ">" line is the contact\'s own words and stays verbatim', () => {
    render(<ChatTranscript messages={[message({ message: '> not a quote\nhi' })]} />);
    expect(screen.queryByTestId('quoted-context')).toBeNull();
    expect(screen.getByText(/> not a quote/)).toBeInTheDocument();
  });
});
