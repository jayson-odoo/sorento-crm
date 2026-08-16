/**
 * Scroll-back + in-thread search on the SHARED chat list (UAC AC-L7 / AC-L8).
 *
 * jsdom has no layout engine, so `scrollHeight` is stubbed per element - that is
 * exactly the quantity the anchoring maths reads, so stubbing it is what makes
 * the "viewport must not jump" guarantee testable at all.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

/**
 * jsdom has no `scrollIntoView`; some suites stub it on the prototype and the
 * stub outlives the test. These suites decide for themselves whether the
 * component can scroll, because that is what arms the open-time settle guard.
 */
function withScrollIntoView() {
  const scrollIntoView = vi.fn();
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    value: scrollIntoView,
    configurable: true,
    writable: true,
  });
  return scrollIntoView;
}

function withoutScrollIntoView() {
  Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
}

/** Longer than the component's post-scroll settle window. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 500));

describe('RespondChatList scroll-back (AC-L7)', () => {
  beforeEach(withoutScrollIntoView);

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

  it('collapses a burst of scroll events into one page request', () => {
    // FINDING 5: scroll fires per frame and the `isLoadingOlder` prop only
    // arrives a render later, so the state guard let a burst stack pages.
    const onLoadOlder = vi.fn();
    render(<RespondChatList items={[msg(1), msg(2)]} onLoadOlder={onLoadOlder} hasMoreOlder />);
    const container = screen.getByTestId('chat-scroll-container');

    container.scrollTop = 0;
    for (let i = 0; i < 6; i += 1) fireEvent.scroll(container);

    expect(onLoadOlder).toHaveBeenCalledTimes(1);
  });

  it('re-arms once the reader scrolls back down', () => {
    const onLoadOlder = vi.fn();
    render(<RespondChatList items={[msg(1), msg(2)]} onLoadOlder={onLoadOlder} hasMoreOlder />);
    const container = screen.getByTestId('chat-scroll-container');

    container.scrollTop = 0;
    fireEvent.scroll(container);
    container.scrollTop = 600;
    fireEvent.scroll(container);
    container.scrollTop = 0;
    fireEvent.scroll(container);

    expect(onLoadOlder).toHaveBeenCalledTimes(2);
  });

  it('ignores the scroll events its own opening scroll emits', async () => {
    // FINDING 5: a smooth scrollIntoView on open emits scroll events at
    // scrollTop ~ 0, which read as "the reader reached the top".
    withScrollIntoView();
    const onLoadOlder = vi.fn();
    render(
      <RespondChatList
        items={[msg(5), msg(6)]}
        highlightMessageId={String(BASE_US + 5_000_000)}
        onLoadOlder={onLoadOlder}
        hasMoreOlder
      />,
    );
    const container = screen.getByTestId('chat-scroll-container');

    container.scrollTop = 0;
    fireEvent.scroll(container);
    expect(onLoadOlder).not.toHaveBeenCalled();

    await settle();
    fireEvent.scroll(container);
    expect(onLoadOlder).toHaveBeenCalledTimes(1);
  });
});

describe('RespondChatList highlighted enquiry (FINDING 2)', () => {
  const HIGHLIGHT_ID = String(BASE_US + 5_000_000);

  it('scrolls to the enquiry once, and never again when a page is prepended', async () => {
    const scrollIntoView = withScrollIntoView();
    const onLoadOlder = vi.fn();
    const { rerender } = render(
      <RespondChatList
        items={[msg(5), msg(6)]}
        highlightMessageId={HIGHLIGHT_ID}
        onLoadOlder={onLoadOlder}
        hasMoreOlder
      />,
    );
    const container = screen.getByTestId('chat-scroll-container');
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));

    await settle();
    stubScrollHeight(container, 1000);
    container.scrollTop = 20;
    fireEvent.scroll(container);
    expect(onLoadOlder).toHaveBeenCalledTimes(1);

    stubScrollHeight(container, 1500);
    rerender(
      <RespondChatList
        items={[msg(3), msg(4), msg(5), msg(6)]}
        highlightMessageId={HIGHLIGHT_ID}
        onLoadOlder={onLoadOlder}
        hasMoreOlder
      />,
    );

    // The reader keeps their place, and is NOT yanked back to the enquiry.
    expect(container.scrollTop).toBe(520);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it('scrolls again when the drawer switches to another enquiry', async () => {
    const scrollIntoView = withScrollIntoView();
    const { rerender } = render(
      <RespondChatList items={[msg(5), msg(6)]} highlightMessageId={HIGHLIGHT_ID} />,
    );
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));

    rerender(
      <RespondChatList
        items={[msg(5), msg(6)]}
        highlightMessageId={String(BASE_US + 6_000_000)}
      />,
    );

    expect(scrollIntoView).toHaveBeenCalledTimes(2);
  });
});

describe('RespondChatList detached window (FINDING 3)', () => {
  beforeEach(withoutScrollIntoView);

  it('offers no way-back control while the window is on the live tail', () => {
    render(<RespondChatList items={[msg(1)]} />);
    expect(screen.queryByTestId('chat-jump-to-latest')).not.toBeInTheDocument();
  });

  it('offers "Jump to latest" while the window is detached', () => {
    const onJumpToLatest = vi.fn();
    render(<RespondChatList items={[msg(1)]} isDetached onJumpToLatest={onJumpToLatest} />);

    const pill = screen.getByTestId('chat-jump-to-latest');
    fireEvent.click(pill);
    expect(onJumpToLatest).toHaveBeenCalledTimes(1);
  });

  it('says how many live messages the detached window is hiding', () => {
    render(
      <RespondChatList
        items={[msg(1)]}
        isDetached
        onJumpToLatest={vi.fn()}
        newerUnseenCount={3}
      />,
    );
    expect(screen.getByTestId('chat-jump-to-latest')).toHaveTextContent('3 new');
  });

  it('pages forward when the reader reaches the bottom of a detached window', () => {
    const onLoadNewer = vi.fn();
    render(
      <RespondChatList
        items={[msg(1), msg(2)]}
        isDetached
        hasMoreNewer
        onLoadNewer={onLoadNewer}
        onJumpToLatest={vi.fn()}
      />,
    );
    const container = screen.getByTestId('chat-scroll-container');
    stubScrollHeight(container, 1000);
    Object.defineProperty(container, 'clientHeight', { value: 400, configurable: true });

    container.scrollTop = 950;
    fireEvent.scroll(container);

    expect(onLoadNewer).toHaveBeenCalledTimes(1);
  });

  it('does not page forward while the reader is mid-window', () => {
    const onLoadNewer = vi.fn();
    render(
      <RespondChatList
        items={[msg(1), msg(2)]}
        isDetached
        hasMoreNewer
        onLoadNewer={onLoadNewer}
        onJumpToLatest={vi.fn()}
      />,
    );
    const container = screen.getByTestId('chat-scroll-container');
    stubScrollHeight(container, 1000);
    Object.defineProperty(container, 'clientHeight', { value: 400, configurable: true });

    container.scrollTop = 300;
    fireEvent.scroll(container);

    expect(onLoadNewer).not.toHaveBeenCalled();
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

  it('puts a search failure on its own line, so the bar cannot overflow at 375px', () => {
    // FINDING 15: the error sat in the non-wrapping control row as a shrink-0
    // span, pushing the bar wider than the drawer.
    render(
      <RespondChatList
        items={[msg(1)]}
        searchController={searchController({ open: true, query: 'x', error: 'Search failed' })}
      />,
    );

    const error = screen.getByTestId('conversation-search-error');
    expect(error).toHaveTextContent('Search failed');
    expect(error.className).not.toContain('shrink-0');
    expect(error.closest('[data-testid="conversation-search-controls"]')).toBeNull();
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

/**
 * Scroll-to-latest (feedback 2026-08-16, item 4).
 *
 * WhatsApp's behaviour: a round down-arrow above the composer whenever the
 * reader is about a viewport up, in EVERY thread surface - not only in a
 * detached (search-jumped) window, which was the only case that offered a way
 * back. jsdom reports 0 for every layout box, so the container's metrics are
 * stubbed: that IS the quantity the control reads.
 */
function stubMetrics(node: HTMLElement, { scrollHeight = 1000, clientHeight = 300 } = {}) {
  Object.defineProperty(node, 'scrollHeight', { value: scrollHeight, configurable: true });
  Object.defineProperty(node, 'clientHeight', { value: clientHeight, configurable: true });
}

describe('RespondChatList scroll-to-latest', () => {
  beforeEach(withoutScrollIntoView);

  it('stays hidden while the reader is on the live tail', () => {
    render(<RespondChatList items={[msg(1), msg(2)]} />);
    const container = screen.getByTestId('chat-scroll-container');
    stubMetrics(container);
    container.scrollTop = 700; // scrollHeight - clientHeight: at the bottom

    fireEvent.scroll(container);

    expect(screen.queryByTestId('chat-jump-to-latest')).not.toBeInTheDocument();
  });

  it('appears once the reader is more than a viewport up', () => {
    render(<RespondChatList items={[msg(1), msg(2)]} />);
    const container = screen.getByTestId('chat-scroll-container');
    stubMetrics(container);
    container.scrollTop = 300; // 400px from the bottom, one viewport is 300

    fireEvent.scroll(container);

    expect(screen.getByTestId('chat-jump-to-latest')).toBeInTheDocument();
  });

  it('stays hidden just under a viewport up - the tail is still on screen', () => {
    render(<RespondChatList items={[msg(1), msg(2)]} />);
    const container = screen.getByTestId('chat-scroll-container');
    stubMetrics(container);
    container.scrollTop = 500; // 200px from the bottom

    fireEvent.scroll(container);

    expect(screen.queryByTestId('chat-jump-to-latest')).not.toBeInTheDocument();
  });

  it('scrolls back to the tail and hides itself again', () => {
    const scrollIntoView = withScrollIntoView();
    render(<RespondChatList items={[msg(1), msg(2)]} />);
    const container = screen.getByTestId('chat-scroll-container');
    stubMetrics(container);
    container.scrollTop = 0;
    fireEvent.scroll(container);

    fireEvent.click(screen.getByTestId('chat-jump-to-latest'));

    expect(scrollIntoView).toHaveBeenCalled();
    expect(screen.queryByTestId('chat-jump-to-latest')).not.toBeInTheDocument();
  });

  it('a detached window re-attaches instead of merely scrolling', () => {
    const onJumpToLatest = vi.fn();
    const scrollIntoView = withScrollIntoView();
    render(<RespondChatList items={[msg(1)]} isDetached onJumpToLatest={onJumpToLatest} />);
    const container = screen.getByTestId('chat-scroll-container');
    stubMetrics(container);
    container.scrollTop = 0;
    fireEvent.scroll(container);
    const before = scrollIntoView.mock.calls.length;

    fireEvent.click(screen.getByTestId('chat-jump-to-latest'));

    expect(onJumpToLatest).toHaveBeenCalledTimes(1);
    // Re-attaching is the caller's job: the window is replaced, so scrolling
    // the current (stale) one would land on the wrong message.
    expect(scrollIntoView.mock.calls.length).toBe(before);
  });

  it('keeps the unseen-count badge on the one control', () => {
    render(<RespondChatList items={[msg(1), msg(2)]} newerUnseenCount={4} />);
    const container = screen.getByTestId('chat-scroll-container');
    stubMetrics(container);
    container.scrollTop = 0;
    fireEvent.scroll(container);

    expect(screen.getByTestId('chat-jump-to-latest')).toHaveTextContent('4 new');
  });
});
