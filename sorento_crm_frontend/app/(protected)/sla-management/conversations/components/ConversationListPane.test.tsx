import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

/**
 * The Conversations inbox list (UAC AC-N1).
 *
 * The hook is stubbed so this suite is about the SURFACE: tabs, the debounce
 * before a keystroke becomes a query, the keyset "Load more", the selection
 * highlight and every state the CRUD standard asks for.
 */
const inboxQuery = vi.fn();
vi.mock('../hooks/useConversationsInbox', () => ({
  useConversationsInbox: (...args: unknown[]) => inboxQuery(...args),
}));

import ConversationListPane from './ConversationListPane';
import type { ConversationInboxItem } from '../services/conversationsInboxService';

function row(over: Partial<ConversationInboxItem> = {}): ConversationInboxItem {
  return {
    contact_ref: '10025531',
    respond_io_id: '10025531',
    phone: '+60123456789',
    name: 'Aisyah Rahman',
    last_message_at: new Date(Date.now() - 5 * 60_000).toISOString().replace('Z', ''),
    last_message_snippet: 'Yes please send the quote',
    last_message_direction: 'incoming',
    mentioned_at: null,
    open_ticket_count: 2,
    my_open_ticket_count: 1,
    my_open_ticket_id: 'tkt-1',
    ...over,
  };
}

function queryState(over: Record<string, unknown> = {}) {
  return {
    data: { pages: [{ items: [row()], next_cursor: null, has_more: false }] },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    ...over,
  };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  inboxQuery.mockReset();
  inboxQuery.mockReturnValue(queryState());
});

afterEach(() => {
  vi.useRealTimers();
});

function renderPane(props: Partial<React.ComponentProps<typeof ConversationListPane>> = {}) {
  const onSelect = vi.fn();
  const onTabChange = vi.fn();
  render(
    <ConversationListPane
      tab="mine"
      onTabChange={onTabChange}
      selectedRef={null}
      onSelect={onSelect}
      {...props}
    />,
  );
  return { onSelect, onTabChange };
}

describe('ConversationListPane (AC-N1)', () => {
  it('renders a row with name, phone, snippet, relative time and the open-ticket chip', () => {
    renderPane();
    expect(screen.getByText('Aisyah Rahman')).toBeDefined();
    expect(screen.getByText('+60123456789')).toBeDefined();
    expect(screen.getByText('Yes please send the quote')).toBeDefined();
    expect(screen.getByTestId('inbox-open-count-10025531')).toHaveTextContent('2 open');
    expect(screen.getByText('5 minutes ago')).toBeDefined();
    // Direction glyph, and no UUID anywhere in the row.
    expect(screen.getByLabelText('Last message was incoming')).toBeDefined();
    expect(screen.queryByText(/tkt-1/)).toBeNull();
  });

  it('offers the four tabs and reports a change', () => {
    const { onTabChange } = renderPane();
    for (const t of ['mine', 'mentioned', 'unassigned', 'all']) {
      expect(screen.getByTestId(`inbox-tab-${t}`)).toBeDefined();
    }
    expect(screen.getByTestId('inbox-tab-mine')).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(screen.getByTestId('inbox-tab-unassigned'));
    expect(onTabChange).toHaveBeenCalledWith('unassigned');
  });

  it('debounces the search: no query until the typing settles', async () => {
    renderPane();
    expect(inboxQuery).toHaveBeenLastCalledWith('mine', '');

    fireEvent.change(screen.getByTestId('inbox-search'), { target: { value: 'ais' } });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(inboxQuery).toHaveBeenLastCalledWith('mine', '');

    act(() => {
      vi.advanceTimersByTime(150);
    });
    await waitFor(() => expect(inboxQuery).toHaveBeenLastCalledWith('mine', 'ais'));
  });

  it('selects a row and highlights the selected one', () => {
    const { onSelect } = renderPane();
    fireEvent.click(screen.getByTestId('inbox-row-10025531'));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ contact_ref: '10025531' }));

    render(
      <ConversationListPane
        tab="mine"
        onTabChange={vi.fn()}
        selectedRef="10025531"
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getAllByTestId('inbox-row-10025531')[1]).toHaveAttribute(
      'data-selected',
      'true',
    );
  });

  it('pages with the keyset cursor when there is more', () => {
    const fetchNextPage = vi.fn();
    inboxQuery.mockReturnValue(queryState({ hasNextPage: true, fetchNextPage }));
    renderPane();

    fireEvent.click(screen.getByTestId('inbox-load-more'));
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it('pulls the next page when the list is scrolled to the bottom', () => {
    const fetchNextPage = vi.fn();
    inboxQuery.mockReturnValue(queryState({ hasNextPage: true, fetchNextPage }));
    renderPane();

    const scroller = screen.getByTestId('inbox-list-scroll');
    Object.defineProperty(scroller, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(scroller, 'clientHeight', { value: 400, configurable: true });
    Object.defineProperty(scroller, 'scrollTop', { value: 560, configurable: true });
    fireEvent.scroll(scroller);

    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it('loading state', () => {
    inboxQuery.mockReturnValue(queryState({ data: undefined, isLoading: true }));
    renderPane();
    expect(screen.getByTestId('inbox-loading')).toBeDefined();
  });

  it('empty state is per tab, and says so when it is a search that found nothing', async () => {
    inboxQuery.mockReturnValue(
      queryState({ data: { pages: [{ items: [], next_cursor: null, has_more: false }] } }),
    );
    renderPane({ tab: 'mentioned' });
    expect(screen.getByTestId('inbox-empty')).toHaveTextContent(
      'Nobody has mentioned you in a note yet.',
    );

    fireEvent.change(screen.getByTestId('inbox-search'), { target: { value: 'zzz' } });
    act(() => {
      vi.advanceTimersByTime(350);
    });
    await waitFor(() =>
      expect(screen.getByTestId('inbox-empty')).toHaveTextContent('No conversation matches "zzz"'),
    );
  });

  it('error state offers a retry', () => {
    const refetch = vi.fn();
    inboxQuery.mockReturnValue(
      queryState({
        data: undefined,
        isError: true,
        error: new Error('Failed to load conversations'),
        refetch,
      }),
    );
    renderPane();
    expect(screen.getByTestId('inbox-error')).toHaveTextContent('Failed to load conversations');
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
