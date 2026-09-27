/**
 * Reply-to on the ticket resolving thread (#1317): the per-bubble menu
 * (chevron + right click + long press), the swipe-right gesture, and the
 * quoted block an outgoing "> quote" reply renders as.
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from '@/lib/toast';

const BASE_US = 1_786_000_000_000_000;

function msg(i: number, over: Partial<RespondMessageRenderable> = {}): RespondMessageRenderable {
  return {
    messageId: BASE_US + i * 1_000_000,
    traffic: 'incoming',
    message: { type: 'text', text: `body ${i}` },
    status: [],
    ...over,
  };
}

const question = msg(1, { message: { type: 'text', text: 'Is the sink in stock?' } });

function bubbleOf(text: string): HTMLElement {
  return screen.getByText(text).closest('[data-testid="message-bubble"]') as HTMLElement;
}

function touch(el: HTMLElement, type: 'pointerDown' | 'pointerMove' | 'pointerUp', x: number, y = 100) {
  fireEvent[type](el, { pointerType: 'touch', pointerId: 7, clientX: x, clientY: y, button: 0 });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('bubble menu (AC-RT-1..6)', () => {
  it('AC-RT-1: a chevron on the bubble opens Reply, Copy in that order', async () => {
    const onReply = vi.fn();
    render(<RespondChatList items={[question]} contactName="Mr Loo" onReply={onReply} />);

    const chevron = within(bubbleOf('Is the sink in stock?')).getByRole('button', {
      name: 'Message actions',
    });
    fireEvent.pointerDown(chevron, { button: 0, ctrlKey: false });

    const items = await screen.findAllByRole('menuitem');
    expect(items.map((i) => i.textContent?.trim())).toEqual(['Reply', 'Copy']);

    fireEvent.click(items[0]);
    expect(onReply).toHaveBeenCalledWith({
      messageId: String(question.messageId),
      excerpt: 'Is the sink in stock?',
      senderLabel: 'Mr Loo',
    });
  });

  it('AC-RT-2: right click on the bubble opens the same menu', async () => {
    render(<RespondChatList items={[question]} contactName="Mr Loo" onReply={vi.fn()} />);
    fireEvent.contextMenu(bubbleOf('Is the sink in stock?'), { clientX: 20, clientY: 20 });
    const items = await screen.findAllByRole('menuitem');
    expect(items.map((i) => i.textContent?.trim())).toEqual(['Reply', 'Copy']);
  });

  it('AC-RT-4: Copy writes the displayed text (never the quote line) and toasts', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const ours = msg(2, { traffic: 'outgoing', message: { type: 'text', text: '> Is the sink in stock?\nYes, 3 units.' } });
    render(<RespondChatList items={[question, ours]} contactName="Mr Loo" onReply={vi.fn()} />);

    fireEvent.contextMenu(bubbleOf('Yes, 3 units.'), { clientX: 20, clientY: 20 });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Copy' }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith('Yes, 3 units.'));
    expect(toast.success).toHaveBeenCalledWith('Copied');
  });

  it('AC-RT-5: without onReply the menu offers Copy only', async () => {
    render(<RespondChatList items={[question]} />);
    fireEvent.contextMenu(bubbleOf('Is the sink in stock?'), { clientX: 20, clientY: 20 });
    const items = await screen.findAllByRole('menuitem');
    expect(items.map((i) => i.textContent?.trim())).toEqual(['Copy']);
  });

  it('AC-RT-5: an internal note gets no menu', () => {
    render(
      <RespondChatList
        items={[question]}
        onReply={vi.fn()}
        comments={[{ id: 'n1', body: 'call him back', author_name: 'Ann', created_at: '2026-08-01T00:00:00' }]}
      />,
    );
    const note = screen.getByTestId('chat-internal-note');
    expect(within(note).queryByRole('button', { name: 'Message actions' })).toBeNull();
  });

  it('AC-RT-6 (owner answer 3): every surface gets the menu, with no opt-in; read-only = Copy only', async () => {
    // The owner widened the scope on 28 Sep: the menu is on every thread
    // surface, so a bare RespondChatList (the read-only portal draft review)
    // has the chevron and a Copy-only menu, and a swipe moves nothing.
    render(<RespondChatList items={[question]} />);
    const bubble = bubbleOf('Is the sink in stock?');
    expect(within(bubble).getByRole('button', { name: 'Message actions' })).toBeInTheDocument();
    touch(bubble, 'pointerDown', 10);
    touch(bubble, 'pointerMove', 30);
    touch(bubble, 'pointerMove', 80);
    expect(bubble.style.transform).toBe('');
    touch(bubble, 'pointerUp', 80);
    fireEvent.contextMenu(bubble, { clientX: 20, clientY: 20 });
    const items = await screen.findAllByRole('menuitem');
    expect(items.map((i) => i.textContent?.trim())).toEqual(['Copy']);
  });

  it('AC-RT-6: a pending (optimistic) bubble has no menu yet', () => {
    const pending = { ...msg(3, { traffic: 'outgoing', message: { type: 'text', text: 'sending now' } }), source: 'pending' } as RespondMessageRenderable;
    render(<RespondChatList items={[pending]} onReply={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Message actions' })).toBeNull();
  });

  it('AC-RT-11: a touch long press opens the menu', async () => {
    vi.useFakeTimers();
    render(<RespondChatList items={[question]} onReply={vi.fn()} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 50);
    act(() => {
      vi.advanceTimersByTime(800);
    });
    vi.useRealTimers();
    expect(await screen.findByRole('menuitem', { name: 'Reply' })).toBeInTheDocument();
  });
});

describe('swipe right to reply (AC-RT-7..10)', () => {
  it('AC-RT-7/8: the bubble follows the finger and a release past 56px replies once', () => {
    const onReply = vi.fn();
    render(<RespondChatList items={[question]} contactName="Mr Loo" onReply={onReply} />);
    const bubble = bubbleOf('Is the sink in stock?');

    touch(bubble, 'pointerDown', 10);
    touch(bubble, 'pointerMove', 30);
    touch(bubble, 'pointerMove', 80);
    expect(bubble.style.transform).toBe('translateX(70px)');
    const icon = screen.getByTestId('swipe-reply-icon');
    expect(Number(icon.style.opacity)).toBeGreaterThan(0.9);

    touch(bubble, 'pointerUp', 80);
    expect(onReply).toHaveBeenCalledTimes(1);
    expect(onReply.mock.calls[0][0]).toMatchObject({ excerpt: 'Is the sink in stock?' });
    expect(bubble.style.transform).toBe('translateX(0px)');
  });

  it('AC-RT-8: a release at exactly 56px replies (the threshold is inclusive)', () => {
    const onReply = vi.fn();
    render(<RespondChatList items={[question]} onReply={onReply} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 10);
    touch(bubble, 'pointerMove', 30);
    touch(bubble, 'pointerMove', 66);
    expect(bubble.style.transform).toBe('translateX(56px)');
    touch(bubble, 'pointerUp', 66);
    expect(onReply).toHaveBeenCalledTimes(1);
  });

  it('AC-RT-7: travel is capped at 80px', () => {
    render(<RespondChatList items={[question]} onReply={vi.fn()} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 0);
    touch(bubble, 'pointerMove', 30);
    touch(bubble, 'pointerMove', 300);
    expect(bubble.style.transform).toBe('translateX(80px)');
  });

  it('AC-RT-9: a release short of the threshold snaps back and does not reply', () => {
    const onReply = vi.fn();
    render(<RespondChatList items={[question]} onReply={onReply} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 10);
    touch(bubble, 'pointerMove', 30);
    touch(bubble, 'pointerMove', 50);
    expect(bubble.style.transform).toBe('translateX(40px)');
    touch(bubble, 'pointerUp', 50);
    expect(onReply).not.toHaveBeenCalled();
    expect(bubble.style.transform).toBe('translateX(0px)');
  });

  it('AC-RT-9: a cancelled gesture snaps back without replying', () => {
    const onReply = vi.fn();
    render(<RespondChatList items={[question]} onReply={onReply} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 10);
    touch(bubble, 'pointerMove', 30);
    touch(bubble, 'pointerMove', 90);
    fireEvent.pointerCancel(bubble, { pointerType: 'touch', pointerId: 7 });
    expect(onReply).not.toHaveBeenCalled();
    expect(bubble.style.transform).toBe('translateX(0px)');
  });

  it('AC-RT-9: swiping LEFT never moves the bubble', () => {
    render(<RespondChatList items={[question]} onReply={vi.fn()} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 200);
    touch(bubble, 'pointerMove', 100);
    expect(bubble.style.transform === '' || bubble.style.transform === 'translateX(0px)').toBe(true);
  });

  it('AC-RT-10: a mostly vertical drag is a scroll, not a swipe', () => {
    const onReply = vi.fn();
    render(<RespondChatList items={[question]} onReply={onReply} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 10, 100);
    touch(bubble, 'pointerMove', 30, 180);
    touch(bubble, 'pointerMove', 90, 260);
    touch(bubble, 'pointerUp', 90, 260);
    expect(onReply).not.toHaveBeenCalled();
    expect(bubble.style.transform === '' || bubble.style.transform === 'translateX(0px)').toBe(true);
  });

  it('AC-RT-10: a mouse drag never swipes', () => {
    const onReply = vi.fn();
    render(<RespondChatList items={[question]} onReply={onReply} />);
    const bubble = bubbleOf('Is the sink in stock?');
    fireEvent.pointerDown(bubble, { pointerType: 'mouse', pointerId: 1, clientX: 10, clientY: 100, button: 0 });
    fireEvent.pointerMove(bubble, { pointerType: 'mouse', pointerId: 1, clientX: 120, clientY: 100 });
    fireEvent.pointerUp(bubble, { pointerType: 'mouse', pointerId: 1, clientX: 120, clientY: 100 });
    expect(onReply).not.toHaveBeenCalled();
  });

  it('no swipe at all when replying is not offered', () => {
    render(<RespondChatList items={[question]} />);
    const bubble = bubbleOf('Is the sink in stock?');
    touch(bubble, 'pointerDown', 10);
    touch(bubble, 'pointerMove', 30);
    touch(bubble, 'pointerMove', 90);
    expect(bubble.style.transform === '' || bubble.style.transform === 'translateX(0px)').toBe(true);
  });
});

describe('quoted reply rendering (AC-RT-20..23)', () => {
  it('AC-RT-20/21: an outgoing "> quote" reply renders a quoted block naming the contact, never raw ">"', () => {
    const ours = msg(2, {
      traffic: 'outgoing',
      message: { type: 'text', text: '> Is the sink in stock?\nYes, 3 units.' },
    });
    render(<RespondChatList items={[question, ours]} contactName="Mr Loo" />);

    const block = screen.getByTestId('quoted-context');
    expect(block).toHaveTextContent(/Replying to Mr Loo/);
    expect(block).toHaveTextContent('Is the sink in stock?');
    expect(screen.getByText('Yes, 3 units.')).toBeInTheDocument();
    expect(screen.queryByText(/^> /)).toBeNull();
    expect(document.body.textContent).not.toContain('> Is the sink');
  });

  it('R2 (owner answer 2): a long quote is compact on the bubble, the reply text dominant', () => {
    const long = 'Please check the sink model ABC-1234 with the chrome finish and the matching waste kit, plus the two mixer taps we spoke about last week and the delivery date';
    const ours = msg(2, {
      traffic: 'outgoing',
      message: { type: 'text', text: `> ${long}\nYes, 3 units.` },
    });
    render(<RespondChatList items={[question, ours]} contactName="Mr Loo" />);

    const block = screen.getByTestId('quoted-context');
    const excerpt = within(block).getByTestId('quoted-context-excerpt');
    // One or two lines, the rest clipped: a two-line clamp in the small size.
    expect(excerpt).toHaveClass('line-clamp-2');
    expect(excerpt).not.toHaveClass('line-clamp-3');
    expect(block).toHaveClass('text-xs');
    // The full quote stays reachable as a tooltip rather than on screen.
    expect(excerpt).toHaveAttribute('title', long);
    // The answer is the bubble's own full-size text, not inside the quote.
    const answer = screen.getByText('Yes, 3 units.');
    expect(block.contains(answer)).toBe(false);
    expect(bubbleOf('Yes, 3 units.')).toHaveClass('text-sm');
  });

  it('AC-RT-22: tapping the block scrolls to the original and flashes it', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const ours = msg(2, {
      traffic: 'outgoing',
      message: { type: 'text', text: '> Is the sink in stock?\nYes, 3 units.' },
    });
    render(<RespondChatList items={[question, ours]} contactName="Mr Loo" />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).toBe('BUTTON');
    scrollIntoView.mockClear();
    fireEvent.click(block);
    expect(scrollIntoView).toHaveBeenCalled();
    const target = scrollIntoView.mock.instances[0] as unknown as HTMLElement;
    expect(target.getAttribute('data-message-id')).toBe(String(question.messageId));
    const original = document.querySelector(
      `[data-message-id="${question.messageId}"] [data-testid="message-bubble"]`,
    ) as HTMLElement;
    expect(original.className).toContain('ring-emerald-500');
  });

  it('AC-RT-21/22: a quote with no loaded original reads "Replying to" and is not a button', () => {
    const ours = msg(2, {
      traffic: 'outgoing',
      message: { type: 'text', text: '> something from last month\nDone.' },
    });
    render(<RespondChatList items={[question, ours]} contactName="Mr Loo" />);
    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).toBe('DIV');
    expect(block).toHaveTextContent(/^Replying to\s*something from last month$/);
  });

  it('AC-RT-21: quoting our own message names the agent side', () => {
    const earlier = msg(1, { traffic: 'outgoing', message: { type: 'text', text: 'Ships Tuesday.' } });
    const ours = msg(2, { traffic: 'outgoing', message: { type: 'text', text: '> Ships Tuesday.\nCorrection: Wednesday.' } });
    render(<RespondChatList items={[earlier, ours]} contactName="Mr Loo" />);
    expect(screen.getByTestId('quoted-context')).toHaveTextContent(/Replying to Sorento/);
  });

  it('AC-RT-20: an inbound message starting with ">" renders verbatim', () => {
    const theirs = msg(2, { message: { type: 'text', text: '> not a quote of ours\nhi' } });
    render(<RespondChatList items={[theirs]} />);
    expect(screen.queryByTestId('quoted-context')).toBeNull();
  });

  it('AC-RT-23: a structured replyTo wins; one quote block per bubble', () => {
    const ours = msg(2, {
      traffic: 'outgoing',
      message: { type: 'text', text: '> Is the sink in stock?\nYes.' },
      replyTo: { id: question.messageId, message: { type: 'text', text: 'Is the sink in stock?' }, traffic: 'incoming' },
    });
    render(<RespondChatList items={[question, ours]} contactName="Mr Loo" />);
    expect(screen.getAllByTestId('quoted-context')).toHaveLength(1);
  });
});
