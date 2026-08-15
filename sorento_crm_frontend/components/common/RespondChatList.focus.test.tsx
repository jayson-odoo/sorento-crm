/**
 * Caller-driven scroll target on the shared chat list (UAC AC-N6).
 *
 * The drawer's quoted enquiry hands `focusMessageId` + `focusNonce` down from
 * `useConversationThread`. What is pinned here: the nonce is the trigger (so a
 * repeat click scrolls again), the bubble gets the flash ring, and a target
 * that has not mounted yet is scrolled to as soon as it does - the around-page
 * lands a render later than the request.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

const BASE_US = 1_786_000_000_000_000;

function msg(i: number): RespondMessageRenderable {
  return {
    messageId: BASE_US + i * 1_000_000,
    traffic: 'incoming',
    message: { type: 'text', text: `body ${i}` },
    status: [],
  };
}

const idOf = (i: number) => String(BASE_US + i * 1_000_000);

let scrollIntoView: ReturnType<typeof vi.fn>;

beforeEach(() => {
  scrollIntoView = vi.fn();
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    value: scrollIntoView,
    configurable: true,
    writable: true,
  });
});

afterEach(() => {
  Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
});

/**
 * Only the CENTRE scrolls are a focus jump. The list also pins itself to the
 * newest message with a plain `{ behavior: 'smooth' }` on the end marker, and
 * counting those would make this suite measure the wrong thing.
 */
function centreScrolls(): number {
  return scrollIntoView.mock.calls.filter(
    ([opts]) => (opts as ScrollIntoViewOptions | undefined)?.block === 'center',
  ).length;
}

function bubbleOf(container: HTMLElement, i: number): HTMLElement {
  const node = container.querySelector(`[data-message-id="${idOf(i)}"]`);
  if (!node) throw new Error(`bubble ${i} not rendered`);
  return node as HTMLElement;
}

describe('RespondChatList focus target (AC-N6)', () => {
  it('does nothing without a nonce', () => {
    render(<RespondChatList items={[msg(1), msg(2)]} contactName="X" focusMessageId={idOf(1)} />);
    expect(centreScrolls()).toBe(0);
  });

  it('scrolls to the requested bubble and rings it', () => {
    const { container } = render(
      <RespondChatList
        items={[msg(1), msg(2)]}
        contactName="X"
        focusMessageId={idOf(1)}
        focusNonce={1}
      />,
    );

    expect(centreScrolls()).toBe(1);
    expect(bubbleOf(container, 1).innerHTML).toContain('ring-emerald-500');
  });

  it('a repeat request with a new nonce scrolls again', () => {
    const { rerender } = render(
      <RespondChatList
        items={[msg(1), msg(2)]}
        contactName="X"
        focusMessageId={idOf(1)}
        focusNonce={1}
      />,
    );
    expect(centreScrolls()).toBe(1);

    // Same id, same items: only the nonce moved.
    rerender(
      <RespondChatList
        items={[msg(1), msg(2)]}
        contactName="X"
        focusMessageId={idOf(1)}
        focusNonce={2}
      />,
    );
    expect(centreScrolls()).toBe(2);
  });

  it('waits for a target that is not in the window yet, then scrolls once it is', () => {
    const { rerender } = render(
      <RespondChatList
        items={[msg(8), msg(9)]}
        contactName="X"
        focusMessageId={idOf(3)}
        focusNonce={1}
      />,
    );
    expect(centreScrolls()).toBe(0);

    // The around-page landed: the window now holds the target.
    rerender(
      <RespondChatList
        items={[msg(2), msg(3), msg(4)]}
        contactName="X"
        focusMessageId={idOf(3)}
        focusNonce={1}
      />,
    );

    expect(centreScrolls()).toBe(1);
    expect(screen.getByText('body 3')).toBeDefined();
  });
});
