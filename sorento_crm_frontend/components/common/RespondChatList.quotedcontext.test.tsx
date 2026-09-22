/**
 * Inbound quote rendering on the SHARED chat list (UAC AC-L6, slice S4.6).
 *
 * A contact's quote-reply arrives as Respond's structured `replyTo`, never as
 * the ">" text convention we write on our own outgoing sends - so it is read
 * from the field, not parsed out of the body.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

const BASE_US = 1_786_000_000_000_000;

function msg(
  i: number,
  over: Partial<RespondMessageRenderable> = {},
): RespondMessageRenderable {
  return {
    messageId: BASE_US + i * 1_000_000,
    traffic: 'incoming',
    message: { type: 'text', text: `body ${i}` },
    status: [],
    ...over,
  };
}

describe('RespondChatList inbound quote rendering (AC-L6)', () => {
  it('shows the quoted excerpt above the body of the quoting message', () => {
    const quoted = msg(1, { traffic: 'outgoing', message: { type: 'text', text: 'Your order ships Tuesday.' } });
    const reply = msg(2, {
      message: { type: 'text', text: 'Which courier?' },
      replyTo: {
        messageId: quoted.messageId,
        traffic: 'outgoing',
        message: { type: 'text', text: 'Your order ships Tuesday.' },
      },
    });
    render(<RespondChatList items={[quoted, reply]} />);

    const blocks = screen.getAllByTestId('quoted-context');
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toHaveTextContent('Your order ships Tuesday.');
    // Not "You": the quoted outgoing message may be a colleague's, and here it
    // carries no known automated source, so it reads as the company.
    expect(blocks[0]).toHaveTextContent(/Replying to Sorento/i);
    // The body itself is untouched.
    expect(screen.getByText('Which courier?')).toBeInTheDocument();
  });

  it('scrolls to the quoted message when it is loaded, and flashes it (real wire shape: replyTo.id, no messageId)', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    const quoted = msg(1, { message: { type: 'text', text: 'Here is my receipt.' } });
    const reply = msg(2, {
      message: { type: 'text', text: 'Thanks!' },
      // Fix round 3: the LIVE Respond relay's replyTo has NO `messageId` key
      // at all - only `id` - switched here so this suite cannot regress to
      // messageId-only fixtures the way it did the first time round.
      replyTo: {
        id: quoted.messageId,
        mId: 'wamid.abc123',
        message: { type: 'text', text: 'Here is my receipt.' },
        sender: { source: 'contact' },
      },
    });
    render(<RespondChatList items={[quoted, reply]} />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).toBe('BUTTON');
    scrollIntoView.mockClear();
    fireEvent.click(block);

    expect(scrollIntoView).toHaveBeenCalled();
  });

  it('renders as plain text (no click affordance) when the quoted message is outside the loaded window', () => {
    const reply = msg(2, {
      message: { type: 'text', text: 'Still waiting on this' },
      replyTo: {
        messageId: BASE_US - 999_000_000,
        message: { type: 'text', text: 'An old message nobody scrolled back to' },
      },
    });
    render(<RespondChatList items={[reply]} />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).not.toBe('BUTTON');
    expect(block).toHaveTextContent('An old message nobody scrolled back to');
  });

  it('falls back to a typed placeholder when the quoted message carried no text', () => {
    const reply = msg(2, {
      message: { type: 'text', text: 'Is this the right one?' },
      replyTo: { messageId: BASE_US, message: { type: 'image' } },
    });
    render(<RespondChatList items={[reply]} />);

    expect(screen.getByTestId('quoted-context')).toHaveTextContent('[image]');
  });

  // A machine send is deliberately unlabelled in a bubble, so the quote block
  // has no sender name to borrow and reads as the company - which is still the
  // point of the rule: never claim the reader wrote it.
  it('attributes an automated sender to the company, not to the reader', () => {
    const quoted = msg(1, {
      traffic: 'outgoing',
      sender: { source: 'ai_agent' },
      message: { type: 'text', text: 'Our showroom opens at 10am.' },
    });
    const reply = msg(2, {
      message: { type: 'text', text: 'Thanks' },
      replyTo: {
        messageId: quoted.messageId,
        traffic: 'outgoing',
        message: { type: 'text', text: 'Our showroom opens at 10am.' },
      },
    });
    render(<RespondChatList items={[quoted, reply]} />);

    expect(screen.getByTestId('quoted-context')).toHaveTextContent(/Replying to Sorento/i);
  });

  it('renders nothing extra on a message with no quote', () => {
    render(<RespondChatList items={[msg(1)]} />);
    expect(screen.queryByTestId('quoted-context')).not.toBeInTheDocument();
  });

  it('never crashes on a malformed replyTo', () => {
    const reply = msg(2, {
      replyTo: {} as RespondMessageRenderable['replyTo'],
    });
    render(<RespondChatList items={[reply]} />);
    expect(screen.queryByTestId('quoted-context')).not.toBeInTheDocument();
    expect(screen.getByText('body 2')).toBeInTheDocument();
  });

  it('prefers the structured quote over our own ">" prefix on an outgoing message', () => {
    const outgoing = msg(3, {
      traffic: 'outgoing',
      message: { type: 'text', text: '> the old emulation\nthe actual reply' },
      replyTo: { messageId: BASE_US, message: { type: 'text', text: 'the real reference' } },
    });
    render(<RespondChatList items={[outgoing]} />);

    const blocks = screen.getAllByTestId('quoted-context');
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toHaveTextContent('the real reference');
    expect(screen.queryByText('the old emulation')).not.toBeInTheDocument();
  });
});

/**
 * R4: reply-to jump on a quote whose target is outside the loaded window
 * reuses the caller's search-jump fetch-back loader, rather than staying
 * inert or building a second one (UAC AC-CP-8/9/10).
 */
describe('RespondChatList reply-to jump beyond the loaded window (AC-CP-8/9/10)', () => {
  it('AC-CP-8: a message id already in the loaded window is a button that scrolls to it locally, without bothering the fetch-back loader', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const onJumpToMessage = vi.fn();

    const quoted = msg(1, { message: { type: 'text', text: 'Here is my receipt.' } });
    const reply = msg(2, {
      message: { type: 'text', text: 'Thanks!' },
      replyTo: { messageId: quoted.messageId, message: { type: 'text', text: 'Here is my receipt.' } },
    });
    render(<RespondChatList items={[quoted, reply]} onJumpToMessage={onJumpToMessage} />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).toBe('BUTTON');
    scrollIntoView.mockClear();
    fireEvent.click(block);

    expect(scrollIntoView).toHaveBeenCalled();
    expect(onJumpToMessage).not.toHaveBeenCalled();
  });

  it('AC-CP-9: a message id outside the loaded window is still a button, and clicking it calls the fetch-back loader with that id', () => {
    const onJumpToMessage = vi.fn();
    const targetId = String(BASE_US - 999_000_000);
    const reply = msg(2, {
      message: { type: 'text', text: 'Still waiting on this' },
      replyTo: {
        messageId: BASE_US - 999_000_000,
        message: { type: 'text', text: 'An old message nobody scrolled back to' },
      },
    });
    render(<RespondChatList items={[reply]} onJumpToMessage={onJumpToMessage} />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).toBe('BUTTON');
    fireEvent.click(block);

    expect(onJumpToMessage).toHaveBeenCalledWith(targetId);
  });

  it('AC-CP-9: once the fetch-back page lands, the target bubble is scrolled to even when the window is replaced by another SAME-SIZE page (B1)', () => {
    // The caller's `useConversationThread.jumpToMessage` sets `focusNonce` ONCE,
    // synchronously, before the around-page fetch resolves - the target is not
    // in `items` yet on that render. The page then lands as a SEPARATE prop
    // update (a same-size window replacing the old one, not appended to it),
    // with focusNonce and focusMessageId both UNCHANGED. If the focus effect's
    // dependency were `sortedItems.length` (50 in, 50 out), that second render
    // would never re-fire it, and the bubble would never be reached.
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    const targetMessageId = BASE_US - 999_000_000;
    const targetId = String(targetMessageId);
    const initialItems = Array.from({ length: 50 }, (_, i) => msg(i + 1));
    // Same length (50), now containing the target in place of the first item -
    // exactly the shape of an `around` page replacing the old window.
    const pageItems = [msg(0, { messageId: targetMessageId }), ...initialItems.slice(1)];
    expect(pageItems).toHaveLength(initialItems.length);

    const { rerender } = render(
      <RespondChatList items={initialItems} focusMessageId={targetId} focusNonce={1} />,
    );
    scrollIntoView.mockClear();

    rerender(<RespondChatList items={pageItems} focusMessageId={targetId} focusNonce={1} />);

    // The specific call shape the focus effect makes (`block: 'center'`)
    // distinguishes it from the unrelated pin-to-bottom scroll, which never
    // passes a `block` option.
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
  });

  it('AC-CP-9: without a fetch-back loader supplied, an out-of-window quote stays plain text (no dead button)', () => {
    const reply = msg(2, {
      message: { type: 'text', text: 'Still waiting on this' },
      replyTo: {
        messageId: BASE_US - 999_000_000,
        message: { type: 'text', text: 'An old message nobody scrolled back to' },
      },
    });
    render(<RespondChatList items={[reply]} />);

    expect(screen.getByTestId('quoted-context').tagName).not.toBe('BUTTON');
  });

  it('AC-CP-10: a quote with no message id at all stays inert, even with a fetch-back loader supplied', () => {
    const reply = msg(2, {
      message: { type: 'text', text: 'Still waiting' },
      replyTo: { message: { type: 'text', text: 'no id on this one' } },
    });
    render(<RespondChatList items={[reply]} onJumpToMessage={vi.fn()} />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).not.toBe('BUTTON');
    expect(block).toHaveTextContent('no id on this one');
  });

  // Fix round 3 (browser pass FAIL, real defect): the LIVE Respond relay's
  // `replyTo` carries the quoted message's id as `id`, never `messageId` -
  // `"replyTo": {"id": 1788922281019104, "message": {...}, "mId": "...",
  // "sender": {...}}`, verified against a real payload in the browser.
  // Every fixture above used `messageId`, which is exactly why they stayed
  // green while every quote in production rendered as an inert div.
  it('AC-CP-21: real wire shape (replyTo.id, no messageId) with the target in the loaded window is a button, and click scrolls', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    const quoted = msg(1, { message: { type: 'text', text: 'Here is my receipt.' } });
    const reply = msg(2, {
      message: { type: 'text', text: 'Thanks!' },
      replyTo: {
        id: quoted.messageId,
        mId: 'wamid.real123',
        message: { type: 'text', text: 'Here is my receipt.' },
        sender: { source: 'contact' },
      },
    });
    render(<RespondChatList items={[quoted, reply]} />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).toBe('BUTTON');
    scrollIntoView.mockClear();
    fireEvent.click(block);

    expect(scrollIntoView).toHaveBeenCalled();
  });

  it('AC-CP-22: real wire shape (replyTo.id, no messageId) with the target outside the loaded window still calls the fetch-back loader, with the id as a string', () => {
    const onJumpToMessage = vi.fn();
    const targetId = BASE_US - 999_000_000;
    const reply = msg(2, {
      message: { type: 'text', text: 'Still waiting on this' },
      replyTo: {
        id: targetId,
        mId: 'wamid.real456',
        message: { type: 'text', text: 'An old message nobody scrolled back to' },
        sender: { source: 'contact' },
      },
    });
    render(<RespondChatList items={[reply]} onJumpToMessage={onJumpToMessage} />);

    const block = screen.getByTestId('quoted-context');
    expect(block.tagName).toBe('BUTTON');
    fireEvent.click(block);

    expect(onJumpToMessage).toHaveBeenCalledWith(String(targetId));
  });
});
