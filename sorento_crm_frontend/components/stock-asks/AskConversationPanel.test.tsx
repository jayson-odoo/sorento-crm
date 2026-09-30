/**
 * AC-ST307 as reshaped by ASKS-UX item 3 (AC-AU10 to AC-AU12): the body of the opened card
 * (portal Drawer, CRM Sheet). The conversation is the SHARED thread (`RespondChatList` driven by
 * `useConversationThread`), fed by the mount's loaders and live tail; the panel owns nothing
 * about fetching. Bubbles carry `data-message-id` (the shared list's own hook); the tagged one
 * reads "This enquiry".
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AskConversationPanel, type AskThreadSource } from './AskConversationPanel';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { StockAsk } from '@/lib/stock-asks';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
const motion = vi.hoisted(() => ({ reduced: false }));
vi.mock('@/lib/motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/motion')>();
  return { ...actual, useReducedMotion: () => motion.reduced };
});

const ASK: StockAsk & { contact_phone?: string | null } = {
  id: 'ask-1',
  customer_name: 'Hock Lee Trading',
  contact_name: 'Ah Seng',
  contact_phone: '+60 12-000 0002',
  product_code: 'SRT5674',
  product_name: 'Wiper Blade 24in',
  quantity: 50,
  branch: 'in_stock',
  answer_summary: 'SRT5674 x 50: yes, we have stock. Please refer to your salesman.',
  notified_agent: true,
  notify_skip_reason: null,
  state: 'open',
  note: 'Called Ah Seng',
  created_at: '2026-09-27T03:00:00Z',
  updated_at: null,
};
const DONE: StockAsk = { ...ASK, state: 'done', done_by: 'Sean Ibrahim', done_at: '2026-09-29T02:00:00Z' };

/** Respond message ids are epoch microseconds; the list reads the bubble clock off them. */
const BASE_US = 1_790_000_000_000_000;
const idOf = (i: number) => String(BASE_US + i * 60_000_000);
function msg(i: number, text: string, traffic: 'incoming' | 'outgoing' = 'incoming'): RespondMessageRenderable {
  return { messageId: BASE_US + i * 60_000_000, traffic, message: { type: 'text', text }, status: [] };
}

const TAIL = [
  msg(1, 'Boss, SRT5674 ada stock?'),
  msg(2, 'How many units do you need?', 'outgoing'),
  msg(3, 'SRT5674 x 50: yes, we have stock', 'outgoing'),
  msg(4, 'ok tq, I call Sean'),
];
const ANCHOR = { messages: [], ask_message_id: 3, ask_message_ref: idOf(3) };

let scrollIntoView: ReturnType<typeof vi.fn>;
beforeEach(() => {
  motion.reduced = false;
  scrollIntoView = vi.fn();
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { value: scrollIntoView, configurable: true, writable: true });
});
afterEach(() => {
  Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
});
/** Only the centre scrolls are a jump; the list also pins itself to the tail on the end marker. */
const centreScrolls = () =>
  scrollIntoView.mock.calls.filter(([opts]) => (opts as ScrollIntoViewOptions | undefined)?.block === 'center').length;

function thread(over: Partial<AskThreadSource> = {}): AskThreadSource {
  return {
    liveItems: TAIL,
    loading: false,
    error: null,
    loadPage: vi.fn().mockResolvedValue({
      items: TAIL,
      has_more_older: false,
      has_more_newer: false,
      oldest_message_id: idOf(1),
      newest_message_id: idOf(4),
    }),
    searchMessages: vi.fn().mockResolvedValue([]),
    ...over,
  };
}

function setup(over: Partial<React.ComponentProps<typeof AskConversationPanel>> = {}) {
  const handlers = { onNote: vi.fn().mockResolvedValue(undefined), onDone: vi.fn(), onReopen: vi.fn() };
  const props = { ask: ASK, conversation: ANCHOR, thread: thread(), showOpenInConversations: false, ...handlers, ...over };
  const view = render(<AskConversationPanel {...props} />);
  return { ...handlers, ...view, props };
}

const bubble = (container: HTMLElement, i: number) => container.querySelector(`[data-message-id="${idOf(i)}"]`) as HTMLElement | null;

describe('AskConversationPanel header and block (AC-ST307)', () => {
  it('shows customer, contact with its phone, and "Asked <datetime>"', () => {
    const { container } = setup();
    const text = (container.textContent ?? '').replace(/\s+/g, ' ');
    expect(screen.getByText('Hock Lee Trading')).toBeInTheDocument();
    expect(text).toContain('Ah Seng');
    expect(text).toContain('+60 12-000 0002');
    expect(text).toContain(`Asked ${formatDateTimeInMalaysia(ASK.created_at)}`);
  });

  it('shows the agent code only when agentCode is passed', () => {
    const { unmount } = setup({ agentCode: 'SEAN I' });
    expect(screen.getByText(/SEAN I/)).toBeInTheDocument();
    unmount();
    const { container } = setup();
    expect(container.textContent).not.toContain('SEAN I');
  });

  it('shows the Asked / Answered block with a Jump to message button', () => {
    const { container } = setup();
    const text = (container.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain('SRT5674 x 50 (Wiper Blade 24in)');
    expect(text).toContain('Answered');
    expect(text).toContain('Yes, we have stock. Please refer to your salesman.');
    expect(screen.getByRole('button', { name: /Jump to message/ })).toBeInTheDocument();
  });

  it('puts nothing after the code when there is no product name', () => {
    const { container } = setup({ ask: { ...ASK, product_name: null } });
    expect(container.textContent).not.toMatch(/\(\s*\)|\(null\)/);
    expect(container.textContent).not.toContain('Wiper Blade');
  });
});

describe('AskConversationPanel conversation is the shared thread (AC-AU10, AC-AU11)', () => {
  it('renders the live tail as the shared chat list with the search affordance, and no "Show the whole day"', () => {
    const { container } = setup();
    expect(screen.getByTestId('chat-scroll-container')).toBeInTheDocument();
    for (const i of [1, 2, 3, 4]) expect(bubble(container, i)).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Search messages' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show the whole day' })).toBeNull();
    // The chat header names the contact, never the customer.
    expect(within(screen.getByTestId('chat-scroll-container').parentElement as HTMLElement).getAllByText('Ah Seng').length).toBeGreaterThan(0);
  });

  it('tags only the anchor bubble "This enquiry" and jumps to it on open', async () => {
    const { container } = setup();
    expect(screen.getAllByText('This enquiry')).toHaveLength(1);
    expect(bubble(container, 3)!.textContent).toContain('This enquiry');
    expect(bubble(container, 3)!.textContent).toContain('SRT5674 x 50: yes, we have stock');
    await waitFor(() => expect(centreScrolls()).toBeGreaterThanOrEqual(1));
  });

  it('tags nothing and disables Jump to message without an anchor', () => {
    setup({ conversation: { messages: [], ask_message_id: null, ask_message_ref: null } });
    expect(screen.queryByText('This enquiry')).toBeNull();
    expect(screen.getByRole('button', { name: /Jump to message/ })).toBeDisabled();
  });

  it('Jump to message scrolls to the anchor again when it is loaded', async () => {
    setup();
    await waitFor(() => expect(centreScrolls()).toBeGreaterThanOrEqual(1));
    const before = centreScrolls();
    fireEvent.click(screen.getByRole('button', { name: /Jump to message/ }));
    await waitFor(() => expect(centreScrolls()).toBe(before + 1));
  });

  it('jumps without motion when the reader asked for reduced motion (DESIGN-LANGUAGE)', async () => {
    motion.reduced = true;
    setup();
    await waitFor(() => expect(centreScrolls()).toBeGreaterThanOrEqual(1));
    fireEvent.click(screen.getByRole('button', { name: /Jump to message/ }));
    await waitFor(() => expect(centreScrolls()).toBeGreaterThanOrEqual(2));
    for (const [opts] of scrollIntoView.mock.calls) {
      expect((opts as ScrollIntoViewOptions | undefined)?.behavior ?? 'auto').toBe('auto');
    }
  });

  it('loads the page around the anchor when the tail does not hold it (an old ask)', async () => {
    const around = [msg(-40, 'long ago'), msg(-39, 'SRT5674 x 50: yes, we have stock', 'outgoing'), msg(-38, 'noted')];
    const loadPage = vi.fn().mockResolvedValue({
      items: around,
      has_more_older: true,
      has_more_newer: true,
      oldest_message_id: idOf(-40),
      newest_message_id: idOf(-38),
      anchor_message_id: idOf(-39),
    });
    const { container } = setup({
      conversation: { messages: [], ask_message_id: 9, ask_message_ref: idOf(-39) },
      thread: thread({ loadPage }),
    });
    await waitFor(() => expect(loadPage).toHaveBeenCalledWith({ around: idOf(-39), limit: 50 }));
    await waitFor(() => expect(bubble(container, -39)).not.toBeNull());
    expect(bubble(container, -39)!.textContent).toContain('This enquiry');
    // The reader is in the past: the way back to the live tail is offered.
    expect(screen.getByTestId('chat-jump-to-latest')).toBeInTheDocument();
  });

  it('shows a loading state while the tail loads, and the thread error when it fails', () => {
    const { unmount } = setup({ thread: thread({ liveItems: [], loading: true }) });
    expect(screen.getByRole('status')).toBeInTheDocument();
    unmount();
    setup({ thread: thread({ liveItems: [], error: 'Server down' }) });
    expect(screen.getByText('Server down')).toBeInTheDocument();
  });

  it('shows no technical fields: no turn ids, delivery status or Respond ids', () => {
    const { container } = setup();
    for (const gone of ['message_id', 'delivery', 'respond', 'turn']) {
      expect((container.textContent ?? '').toLowerCase()).not.toContain(gone);
    }
  });
});

describe('AskConversationPanel Open in Conversations (AC-ST307)', () => {
  it('is a link only when showOpenInConversations is set (the CRM)', () => {
    const { unmount } = setup({ showOpenInConversations: true, conversation: { ...ANCHOR, contact_id: 'contact-7' } });
    expect(screen.getByRole('link', { name: 'Open in Conversations' })).toHaveAttribute('href', '/sla-management/conversations?contact=contact-7');
    unmount();
    setup({ showOpenInConversations: false });
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
    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'Called Ah Seng, delivery Thursday' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }));
    expect(onNote).toHaveBeenCalledWith('ask-1', 'Called Ah Seng, delivery Thursday');
    const saved = await screen.findByText(/Saved\s+\S+/);
    expect(saved.textContent).toMatch(/Saved\s+\d{2}\/\d{2}\/\d{4},?\s+\d{1,2}:\d{2}/);
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
