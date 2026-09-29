/**
 * AC-ST307: the body of the opened card (portal Drawer, CRM Sheet). Presentational: the mount
 * fetches the conversation and owns the drawer.
 *
 * Pinned hooks (the coder must honour them): every message bubble is
 * `data-testid="conversation-bubble"` with `data-direction="in" | "out"`; the flash on Jump to
 * message is a class whose name contains `flash`.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AskConversationPanel } from './AskConversationPanel';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { StockAsk } from '@/lib/stock-asks';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const ASK: StockAsk = {
  id: 'ask-1',
  customer_name: 'Hock Lee Trading',
  contact_name: 'Ah Seng',
  product_code: 'SRT5674',
  product_name: 'Wiper Blade 24in',
  quantity: 50,
  branch: 'in_stock',
  answer_summary: 'SRT5674 x 50: yes, we have stock, please refer to your salesman to proceed.',
  notified_agent: true,
  notify_skip_reason: null,
  state: 'open',
  note: 'Called Ah Seng',
  created_at: '2026-09-27T03:00:00Z',
  updated_at: null,
  agent_code: 'SEAN I',
};
const DONE: StockAsk = { ...ASK, state: 'done', done_by: 'Sean Ibrahim', done_at: '2026-09-29T02:00:00Z' };

const CONVERSATION = {
  messages: [
    { id: 1, direction: 'in', text: 'Boss, SRT5674 ada stock?', at: '2026-09-27T02:58:00' },
    { id: 2, direction: 'out', text: 'How many units do you need?', at: '2026-09-27T02:58:30' },
    { id: 3, direction: 'out', text: 'SRT5674 x 50: yes, we have stock', at: '2026-09-27T03:00:00' },
    { id: 4, direction: 'in', text: 'ok tq, I call Sean', at: '2026-09-27T03:01:00' },
  ],
  ask_message_id: 3,
};

const scrolled: Element[] = [];

beforeEach(() => {
  scrolled.length = 0;
  Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
    scrolled.push(this);
  }) as never;
});
afterEach(() => {
  delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
});

function setup(over: Partial<React.ComponentProps<typeof AskConversationPanel>> = {}) {
  const handlers = {
    onWholeDay: vi.fn(),
    onNote: vi.fn().mockResolvedValue(undefined),
    onDone: vi.fn(),
    onReopen: vi.fn(),
  };
  const view = render(
    <AskConversationPanel
      ask={ASK}
      conversation={CONVERSATION}
      loading={false}
      showOpenInConversations={false}
      {...handlers}
      {...over}
    />,
  );
  return { ...handlers, ...view };
}

const bubbles = () => screen.getAllByTestId('conversation-bubble');

describe('AskConversationPanel header and block (AC-ST307)', () => {
  it('shows customer, contact, the asked-at time and the agent code', () => {
    const { container } = setup();
    expect(screen.getByText('Hock Lee Trading')).toBeInTheDocument();
    expect(container.textContent).toContain('Ah Seng');
    expect(container.textContent).toContain(formatDateTimeInMalaysia(ASK.created_at));
    expect(container.textContent).toContain('SEAN I');
  });

  it('shows the Asked / Answered block with a Jump to message button', () => {
    const { container } = setup();
    const text = (container.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain('Asked');
    expect(text).toContain('SRT5674 x 50');
    expect(text).toContain('Answered');
    expect(text).toContain('Yes, we have stock, please refer to your salesman to proceed.');
    expect(screen.getByRole('button', { name: /Jump to message/ })).toBeInTheDocument();
  });
});

describe('AskConversationPanel conversation (AC-ST307)', () => {
  it('renders inbound bubbles left and outbound right, oldest first', () => {
    setup();
    expect(bubbles().map((b) => [b.getAttribute('data-direction'), (b.textContent ?? '').replace('This ask', '').trim().slice(0, 12)])).toEqual([
      ['in', 'Boss, SRT567'],
      ['out', 'How many uni'],
      ['out', 'SRT5674 x 50'],
      ['in', 'ok tq, I cal'],
    ]);
  });

  it('tags only the ask_message_id bubble "This ask"', () => {
    setup();
    const tagged = bubbles().filter((b) => (b.textContent ?? '').includes('This ask'));
    expect(tagged).toHaveLength(1);
    expect(tagged[0].textContent).toContain('SRT5674 x 50: yes, we have stock');
  });

  it('tags nothing when ask_message_id is null', () => {
    setup({ conversation: { ...CONVERSATION, ask_message_id: null } });
    expect(screen.queryByText('This ask')).toBeNull();
  });

  it('shows a loading state while the conversation loads and no bubbles', () => {
    setup({ conversation: undefined, loading: true });
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryAllByTestId('conversation-bubble')).toHaveLength(0);
  });

  it('shows no technical fields: no turn ids, delivery status or Respond ids', () => {
    const { container } = setup();
    for (const gone of ['message_id', 'delivery', 'respond', 'turn']) {
      expect((container.textContent ?? '').toLowerCase()).not.toContain(gone);
    }
  });

  it('Jump to message scrolls the tagged bubble into view and flashes it', () => {
    setup();
    const tagged = bubbles().find((b) => (b.textContent ?? '').includes('This ask'))!;
    const before = tagged.className;
    expect(before).not.toMatch(/flash/i);
    fireEvent.click(screen.getByRole('button', { name: /Jump to message/ }));
    expect(scrolled).toEqual([tagged]);
    expect(tagged.className).toMatch(/flash/i);
    const others = bubbles().filter((b) => b !== tagged);
    for (const b of others) expect(b.className).not.toMatch(/flash/i);
  });

  it('Show the whole day calls onWholeDay', () => {
    const { onWholeDay } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Show the whole day' }));
    expect(onWholeDay).toHaveBeenCalledTimes(1);
  });
});

describe('AskConversationPanel Open in Conversations (AC-ST307)', () => {
  it('is a link only when showOpenInConversations is set (the CRM)', () => {
    const { unmount } = setup({ showOpenInConversations: true });
    expect(screen.getByRole('link', { name: 'Open in Conversations' })).toBeInTheDocument();
    unmount();
    setup({ showOpenInConversations: false });
    expect(screen.queryByRole('link', { name: 'Open in Conversations' })).toBeNull();
    expect(screen.queryByText('Open in Conversations')).toBeNull();
  });
});

describe('AskConversationPanel note (AC-ST307)', () => {
  it('starts from the ask note; blur alone never saves', () => {
    const { onNote } = setup();
    const box = screen.getByLabelText('Note') as HTMLTextAreaElement;
    expect(box.value).toBe('Called Ah Seng');
    fireEvent.change(box, { target: { value: 'Called Ah Seng, delivery Thursday' } });
    fireEvent.blur(box);
    expect(onNote).not.toHaveBeenCalled();
  });

  it('Save note calls onNote(askId, text) and then shows Saved with a time', async () => {
    const { onNote } = setup();
    expect(screen.queryByText(/Saved\s/)).toBeNull();
    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'Called Ah Seng, delivery Thursday' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }));
    expect(onNote).toHaveBeenCalledWith('ask-1', 'Called Ah Seng, delivery Thursday');
    expect(await screen.findByText(/Saved\s+\S+/)).toBeInTheDocument();
  });
});

describe('AskConversationPanel foot (AC-ST307)', () => {
  it('an open ask has Done at the foot calling onDone(id)', () => {
    const { onDone } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith('ask-1');
    expect(screen.queryByRole('button', { name: 'Reopen' })).toBeNull();
  });

  it('a done ask has Reopen at the foot calling onReopen(id)', async () => {
    const { onReopen } = setup({ ask: DONE });
    expect(screen.queryByRole('button', { name: 'Done' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Reopen' }));
    await waitFor(() => expect(onReopen).toHaveBeenCalledWith('ask-1'));
  });

  it('Done sits after the note in document order (the foot)', () => {
    setup();
    const note = screen.getByLabelText('Note');
    const done = screen.getByRole('button', { name: 'Done' });
    expect(note.compareDocumentPosition(done) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
