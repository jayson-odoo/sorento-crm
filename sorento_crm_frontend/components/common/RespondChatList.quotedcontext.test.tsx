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

  it('scrolls to the quoted message when it is loaded, and flashes it', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    const quoted = msg(1, { message: { type: 'text', text: 'Here is my receipt.' } });
    const reply = msg(2, {
      message: { type: 'text', text: 'Thanks!' },
      replyTo: { messageId: quoted.messageId, message: { type: 'text', text: 'Here is my receipt.' } },
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
