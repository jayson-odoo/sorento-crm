/**
 * Scroll-back + in-thread search on the SHARED chat list (UAC AC-L7 / AC-L8).
 *
 * jsdom has no layout engine, so `scrollHeight` is stubbed per element - that is
 * exactly the quantity the anchoring maths reads, so stubbing it is what makes
 * the "viewport must not jump" guarantee testable at all.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import RespondChatList from './RespondChatList';
import type { ConversationSearchController } from './conversation/useConversationThread';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

const BASE_US = 1_786_000_000_000_000;

function msg(i: number, text = `body ${i}`): RespondMessageRenderable {
  return {
    messageId: BASE_US + i * 1_000_000,
    traffic: 'incoming',
    message: { type: 'text', text },
    status: [],
  };
}

function stubScrollHeight(node: HTMLElement, value: number) {
  Object.defineProperty(node, 'scrollHeight', { value, configurable: true });
}

function searchController(
  overrides: Partial<ConversationSearchController> = {},
): ConversationSearchController {
  return {
    open: false,
    query: '',
    setQuery: vi.fn(),
    openSearch: vi.fn(),
    closeSearch: vi.fn(),
    matchCount: 0,
    activePosition: 0,
    activeMessageId: null,
    isSearching: false,
    isJumping: false,
    error: null,
    next: vi.fn(),
    previous: vi.fn(),
    ...overrides,
  };
}

describe('RespondChatList scroll-back (AC-L7)', () => {
  it('asks for older messages when the reader reaches the top', () => {
    const onLoadOlder = vi.fn();
    render(<RespondChatList items={[msg(1), msg(2)]} onLoadOlder={onLoadOlder} hasMoreOlder />);
    const container = screen.getByTestId('chat-scroll-container');

    container.scrollTop = 10;
    fireEvent.scroll(container);

    expect(onLoadOlder).toHaveBeenCalledTimes(1);
  });

  it('stays quiet while the reader is away from the top', () => {
    const onLoadOlder = vi.fn();
    render(<RespondChatList items={[msg(1), msg(2)]} onLoadOlder={onLoadOlder} hasMoreOlder />);
    const container = screen.getByTestId('chat-scroll-container');

    container.scrollTop = 400;
    fireEvent.scroll(container);

    expect(onLoadOlder).not.toHaveBeenCalled();
  });

  it('stops asking once there is nothing older', () => {
    const onLoadOlder = vi.fn();
    render(
      <RespondChatList items={[msg(1)]} onLoadOlder={onLoadOlder} hasMoreOlder={false} atConversationStart />,
    );
    const container = screen.getByTestId('chat-scroll-container');
    container.scrollTop = 0;
    fireEvent.scroll(container);

    expect(onLoadOlder).not.toHaveBeenCalled();
    expect(screen.getByTestId('chat-conversation-start')).toBeTruthy();
  });

  it('does not stack requests while a page is already loading', () => {
    const onLoadOlder = vi.fn();
    render(<RespondChatList items={[msg(1)]} onLoadOlder={onLoadOlder} hasMoreOlder isLoadingOlder />);
    const container = screen.getByTestId('chat-scroll-container');
    container.scrollTop = 0;
    fireEvent.scroll(container);

    expect(onLoadOlder).not.toHaveBeenCalled();
    expect(screen.getByTestId('chat-older-loading')).toBeTruthy();
  });

  it('holds the reader in place when a page is prepended', () => {
    const onLoadOlder = vi.fn();
    const { rerender } = render(
      <RespondChatList items={[msg(5), msg(6)]} onLoadOlder={onLoadOlder} hasMoreOlder />,
    );
    const container = screen.getByTestId('chat-scroll-container');

    stubScrollHeight(container, 1000);
    container.scrollTop = 20;
    fireEvent.scroll(container);
    expect(onLoadOlder).toHaveBeenCalled();

    // The prepended page makes the content 500px taller.
    stubScrollHeight(container, 1500);
    rerender(
      <RespondChatList
        items={[msg(3), msg(4), msg(5), msg(6)]}
        onLoadOlder={onLoadOlder}
        hasMoreOlder
      />,
    );

    // Same visual position: old offset + exactly the growth above it.
    expect(container.scrollTop).toBe(520);
  });

  it('does not correct scroll for growth that was not a prepend', () => {
    const { rerender } = render(<RespondChatList items={[msg(5)]} hasMoreOlder />);
    const container = screen.getByTestId('chat-scroll-container');
    stubScrollHeight(container, 1000);
    container.scrollTop = 300;

    stubScrollHeight(container, 1400);
    rerender(<RespondChatList items={[msg(5), msg(6)]} hasMoreOlder />);

    expect(container.scrollTop).toBe(300);
  });
});

describe('RespondChatList in-thread search (AC-L8)', () => {
  it('shows no search affordance when no controller is supplied', () => {
    render(<RespondChatList items={[msg(1)]} />);
    expect(screen.queryByLabelText('Search messages')).toBeNull();
  });

  it('opens the search bar from the header icon', () => {
    const controller = searchController();
    render(<RespondChatList items={[msg(1)]} searchController={controller} />);

    fireEvent.click(screen.getByLabelText('Search messages'));
    expect(controller.openSearch).toHaveBeenCalled();
  });

  it('renders the bar with a match counter once open', () => {
    const controller = searchController({
      open: true,
      query: 'order',
      matchCount: 3,
      activePosition: 2,
    });
    render(<RespondChatList items={[msg(1)]} searchController={controller} />);

    expect(screen.getByTestId('conversation-search-counter').textContent).toBe('2 / 3');
  });

  it('says so when a query has no matches', () => {
    const controller = searchController({ open: true, query: 'zzz', matchCount: 0 });
    render(<RespondChatList items={[msg(1)]} searchController={controller} />);
    expect(screen.getByTestId('conversation-search-counter').textContent).toBe('No results');
  });

  it('walks matches with Enter and Shift+Enter, and closes on Escape', () => {
    const controller = searchController({ open: true, query: 'order', matchCount: 2 });
    render(<RespondChatList items={[msg(1)]} searchController={controller} />);
    const input = screen.getByRole('searchbox');

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(controller.next).toHaveBeenCalled();

    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(controller.previous).toHaveBeenCalled();

    fireEvent.keyDown(input, { key: 'Escape' });
    expect(controller.closeSearch).toHaveBeenCalled();
  });

  it('marks the searched term inside the bubble', () => {
    render(
      <RespondChatList
        items={[msg(1, 'where is my order please')]}
        searchController={searchController({ open: true, query: 'order' })}
        highlightTerm="order"
      />,
    );
    const marks = document.querySelectorAll('mark');
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe('order');
  });

  it('does not mark anything when there is no term', () => {
    render(<RespondChatList items={[msg(1, 'where is my order')]} />);
    expect(document.querySelectorAll('mark')).toHaveLength(0);
  });

  it('rings the active match and scrolls it into view', () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      value: scrollIntoView,
      configurable: true,
      writable: true,
    });

    const activeId = String(BASE_US + 2_000_000);
    render(
      <RespondChatList
        items={[msg(1), msg(2), msg(3)]}
        searchController={searchController({ open: true, query: 'x', activeMessageId: activeId })}
      />,
    );

    const ringed = document.querySelector('[data-active-match="true"]');
    expect(ringed).toBeTruthy();
    expect(ringed?.className).toContain('ring-sky-500');
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
  });
});
