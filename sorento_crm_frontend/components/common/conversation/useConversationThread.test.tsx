import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

import {
  mergeThreadItems,
  useConversationThread,
  type ConversationSearchMatch,
  type ConversationThreadLoaders,
  type ConversationThreadPage,
} from './useConversationThread';

type LoadPage = ConversationThreadLoaders['loadPage'];
type SearchMessages = ConversationThreadLoaders['searchMessages'];

/** Respond message ids are epoch MICROseconds, so they also order the thread. */
const BASE_US = 1_786_000_000_000_000;

function msg(index: number, text = `body ${index}`, source?: 'respond' | 'local'): RespondMessageRenderable {
  return {
    messageId: BASE_US + index * 1_000_000,
    traffic: 'incoming',
    message: { type: 'text', text },
    status: [],
    ...(source ? { source } : {}),
  } as RespondMessageRenderable;
}

function page(
  items: RespondMessageRenderable[],
  overrides: Partial<ConversationThreadPage> = {},
): ConversationThreadPage {
  return {
    items,
    has_more_older: true,
    has_more_newer: false,
    oldest_message_id: items.length ? String(items[0].messageId) : null,
    newest_message_id: items.length ? String(items[items.length - 1].messageId) : null,
    ...overrides,
  };
}

describe('mergeThreadItems', () => {
  it('dedupes by message id and keeps oldest-to-newest order', () => {
    const merged = mergeThreadItems([msg(3), msg(1)], [msg(1), msg(2)]);
    expect(merged.map((m) => m.messageId)).toEqual([
      BASE_US + 1_000_000,
      BASE_US + 2_000_000,
      BASE_US + 3_000_000,
    ]);
  });

  it('prefers the Respond-sourced copy over the text-only local mirror', () => {
    const local = { ...msg(1, 'plain text', 'local') };
    const rich = { ...msg(1, 'plain text', 'respond'), message: { type: 'image', text: '' } };
    const merged = mergeThreadItems([local], [rich as RespondMessageRenderable]);
    expect(merged).toHaveLength(1);
    expect(merged[0].message?.type).toBe('image');
  });

  it('keeps items that carry no message id (they cannot be deduped)', () => {
    const anonymous = { traffic: 'incoming', message: { text: 'no id' } } as RespondMessageRenderable;
    expect(mergeThreadItems([msg(1)], [anonymous])).toHaveLength(2);
  });
});

describe('useConversationThread', () => {
  let loadPage: ReturnType<typeof vi.fn<LoadPage>>;
  let searchMessages: ReturnType<typeof vi.fn<SearchMessages>>;

  beforeEach(() => {
    loadPage = vi.fn<LoadPage>();
    searchMessages = vi.fn<SearchMessages>();
  });

  const setup = (liveItems: RespondMessageRenderable[] = [msg(8), msg(9)]) =>
    renderHook(
      (props: { liveItems: RespondMessageRenderable[] }) =>
        useConversationThread({
          liveItems: props.liveItems,
          loadPage,
          searchMessages,
          searchDebounceMs: 0,
        }),
      { initialProps: { liveItems } },
    );

  it('starts from the live window and assumes there is more history', () => {
    const { result } = setup();
    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 8_000_000,
      BASE_US + 9_000_000,
    ]);
    expect(result.current.hasMoreOlder).toBe(true);
    expect(result.current.atConversationStart).toBe(false);
  });

  it('prepends an older page addressed by the oldest loaded message id', async () => {
    loadPage.mockResolvedValue(page([msg(6), msg(7)]));
    const { result } = setup();

    act(() => result.current.loadOlder());

    await waitFor(() => expect(result.current.isLoadingOlder).toBe(false));
    expect(loadPage).toHaveBeenCalledWith({ before: String(BASE_US + 8_000_000), limit: 50 });
    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 6_000_000,
      BASE_US + 7_000_000,
      BASE_US + 8_000_000,
      BASE_US + 9_000_000,
    ]);
  });

  it('never renders a message twice when a page overlaps the live window', async () => {
    loadPage.mockResolvedValue(page([msg(7), msg(8)]));
    const { result } = setup();

    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.isLoadingOlder).toBe(false));

    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 7_000_000,
      BASE_US + 8_000_000,
      BASE_US + 9_000_000,
    ]);
  });

  it('stops asking once a page reports the start of the conversation', async () => {
    loadPage.mockResolvedValue(page([msg(7)], { has_more_older: false }));
    const { result } = setup();

    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.hasMoreOlder).toBe(false));
    expect(result.current.atConversationStart).toBe(true);

    act(() => result.current.loadOlder());
    expect(loadPage).toHaveBeenCalledTimes(1);
  });

  it('does not fire a second request while one is in flight', async () => {
    let resolvePage: (p: ConversationThreadPage) => void = () => {};
    loadPage.mockReturnValue(
      new Promise<ConversationThreadPage>((resolve) => {
        resolvePage = resolve;
      }),
    );
    const { result } = setup();

    act(() => result.current.loadOlder());
    act(() => result.current.loadOlder());
    expect(loadPage).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolvePage(page([msg(7)]));
    });
  });

  it('surfaces a page failure without losing the loaded window', async () => {
    loadPage.mockRejectedValue(new Error('network down'));
    const { result } = setup();

    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.error).toBe('network down'));
    expect(result.current.items).toHaveLength(2);
  });

  it('keeps merging live items while the reader is scrolled up', async () => {
    loadPage.mockResolvedValue(page([msg(6), msg(7)]));
    const { result, rerender } = setup();

    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.items).toHaveLength(4));

    rerender({ liveItems: [msg(8), msg(9), msg(10)] });
    expect(result.current.items.map((m) => m.messageId)).toContain(BASE_US + 10_000_000);
  });

  // ---- search ------------------------------------------------------------

  const matches: ConversationSearchMatch[] = [
    { message_id: String(BASE_US + 9_000_000), sent_at: null, direction: 'incoming', snippet: 'b' },
    { message_id: String(BASE_US + 2_000_000), sent_at: null, direction: 'incoming', snippet: 'a' },
  ];

  it('does not search until the bar is opened', async () => {
    const { result } = setup();
    act(() => result.current.search.setQuery('needle'));
    await new Promise((r) => setTimeout(r, 10));
    expect(searchMessages).not.toHaveBeenCalled();
  });

  it('runs a debounced search and selects the first (newest) match', async () => {
    searchMessages.mockResolvedValue(matches);
    const { result } = setup();

    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));

    await waitFor(() => expect(result.current.search.matchCount).toBe(2));
    expect(searchMessages).toHaveBeenCalledWith('needle');
    expect(result.current.search.activePosition).toBe(1);
    expect(result.current.search.activeMessageId).toBe(String(BASE_US + 9_000_000));
    expect(result.current.highlightTerm).toBe('needle');
  });

  it('collapses a burst of keystrokes into one request', async () => {
    searchMessages.mockResolvedValue([]);
    const { result } = setup();
    act(() => result.current.search.openSearch());

    act(() => result.current.search.setQuery('n'));
    act(() => result.current.search.setQuery('ne'));
    act(() => result.current.search.setQuery('nee'));

    await waitFor(() => expect(searchMessages).toHaveBeenCalledTimes(1));
    expect(searchMessages).toHaveBeenCalledWith('nee');
  });

  it('clears matches when the query is emptied', async () => {
    searchMessages.mockResolvedValue(matches);
    const { result } = setup();
    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));
    await waitFor(() => expect(result.current.search.matchCount).toBe(2));

    act(() => result.current.search.setQuery(''));
    await waitFor(() => expect(result.current.search.matchCount).toBe(0));
    expect(result.current.search.activeMessageId).toBeNull();
  });

  it('walks matches with wrap-around, up toward older and down toward newer', async () => {
    searchMessages.mockResolvedValue(matches);
    loadPage.mockResolvedValue(page([msg(1), msg(2), msg(3)], { has_more_older: true }));
    const { result } = setup();
    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));
    await waitFor(() => expect(result.current.search.matchCount).toBe(2));

    // Down = newer; from the newest match it wraps to the oldest.
    act(() => result.current.search.next());
    expect(result.current.search.activePosition).toBe(2);

    act(() => result.current.search.previous());
    expect(result.current.search.activePosition).toBe(1);
  });

  it('replaces the window with an around-page when the match is not loaded', async () => {
    searchMessages.mockResolvedValue(matches);
    const around = page([msg(1), msg(2), msg(3)], {
      has_more_older: true,
      anchor_message_id: String(BASE_US + 2_000_000),
    });
    loadPage.mockResolvedValue(around);
    const { result } = setup();

    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));
    await waitFor(() => expect(result.current.search.matchCount).toBe(2));

    // Match 1 (id ...9_000_000) IS loaded - no fetch for it.
    expect(loadPage).not.toHaveBeenCalled();

    act(() => result.current.search.next());
    await waitFor(() =>
      expect(loadPage).toHaveBeenCalledWith({ around: String(BASE_US + 2_000_000), limit: 50 }),
    );
    await waitFor(() => expect(result.current.search.isJumping).toBe(false));

    // The window IS the jump page - the live tail is not spliced onto it, or the
    // reader would see a hole between 2026-05 and today.
    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 1_000_000,
      BASE_US + 2_000_000,
      BASE_US + 3_000_000,
    ]);
  });

  it('returns to the live tail when search closes', async () => {
    searchMessages.mockResolvedValue(matches);
    loadPage.mockResolvedValue(page([msg(1), msg(2), msg(3)]));
    const { result } = setup();

    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));
    await waitFor(() => expect(result.current.search.matchCount).toBe(2));
    act(() => result.current.search.next());
    await waitFor(() => expect(result.current.items).toHaveLength(3));

    act(() => result.current.search.closeSearch());
    expect(result.current.search.open).toBe(false);
    expect(result.current.search.query).toBe('');
    expect(result.current.highlightTerm).toBe('');
    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 8_000_000,
      BASE_US + 9_000_000,
    ]);
  });

  it('reports a search failure instead of showing stale matches', async () => {
    searchMessages.mockRejectedValue(new Error('search exploded'));
    const { result } = setup();
    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));

    await waitFor(() => expect(result.current.search.error).toBe('search exploded'));
    expect(result.current.search.matchCount).toBe(0);
  });

  it('ignores a stale page that lands after the window moved on', async () => {
    let resolveFirst: (p: ConversationThreadPage) => void = () => {};
    loadPage.mockReturnValueOnce(
      new Promise<ConversationThreadPage>((resolve) => {
        resolveFirst = resolve;
      }),
    );
    const { result } = setup();

    act(() => result.current.loadOlder());
    // Search closing bumps the sequence: the in-flight page is now obsolete.
    act(() => result.current.search.closeSearch());
    await act(async () => {
      resolveFirst(page([msg(0)]));
    });

    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 8_000_000,
      BASE_US + 9_000_000,
    ]);
  });

  it('discards the window when the conversation changes', async () => {
    loadPage.mockResolvedValue(page([msg(6), msg(7)]));
    const { result, rerender } = renderHook(
      (props: { resetKey: string; liveItems: RespondMessageRenderable[] }) =>
        useConversationThread({
          liveItems: props.liveItems,
          loadPage,
          searchMessages,
          searchDebounceMs: 0,
          resetKey: props.resetKey,
        }),
      { initialProps: { resetKey: 'ticket-a', liveItems: [msg(8), msg(9)] } },
    );

    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.items).toHaveLength(4));

    // Switching tickets in place must not carry one contact's history into
    // another contact's thread.
    rerender({ resetKey: 'ticket-b', liveItems: [msg(20)] });
    expect(result.current.items.map((m) => m.messageId)).toEqual([BASE_US + 20_000_000]);
    expect(result.current.hasMoreOlder).toBe(true);
    expect(result.current.search.open).toBe(false);
  });

  it('releases the older-page flag even when a jump supersedes it', async () => {
    // FINDING 1: the busy flag was cleared inside the sequence guard, so a
    // superseded older page left `isLoadingOlder` true forever - scroll-back
    // silently dead for the rest of the drawer's life.
    searchMessages.mockResolvedValue(matches);
    let resolveOlder: (p: ConversationThreadPage) => void = () => {};
    let resolveJump: (p: ConversationThreadPage) => void = () => {};
    loadPage
      .mockReturnValueOnce(
        new Promise<ConversationThreadPage>((resolve) => {
          resolveOlder = resolve;
        }),
      )
      .mockReturnValueOnce(
        new Promise<ConversationThreadPage>((resolve) => {
          resolveJump = resolve;
        }),
      );
    const { result } = setup();

    act(() => result.current.loadOlder());
    expect(result.current.isLoadingOlder).toBe(true);

    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));
    await waitFor(() => expect(result.current.search.matchCount).toBe(2));
    act(() => result.current.search.next());
    await waitFor(() => expect(result.current.search.isJumping).toBe(true));

    await act(async () => {
      resolveOlder(page([msg(0)]));
    });
    expect(result.current.isLoadingOlder).toBe(false);

    await act(async () => {
      resolveJump(page([msg(1), msg(2), msg(3)]));
    });
    await waitFor(() => expect(result.current.search.isJumping).toBe(false));

    loadPage.mockResolvedValueOnce(page([msg(0)]));
    act(() => result.current.loadOlder());
    expect(loadPage).toHaveBeenCalledTimes(3);
  });

  it('releases the jumping flag even when the jump is superseded', async () => {
    searchMessages.mockResolvedValue(matches);
    let resolveJump: (p: ConversationThreadPage) => void = () => {};
    loadPage.mockReturnValueOnce(
      new Promise<ConversationThreadPage>((resolve) => {
        resolveJump = resolve;
      }),
    );
    const { result } = setup();

    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));
    await waitFor(() => expect(result.current.search.matchCount).toBe(2));
    act(() => result.current.search.next());
    await waitFor(() => expect(result.current.search.isJumping).toBe(true));

    // Anything that moves the window on (here: another older page) bumps the
    // sequence; the jump landing afterwards must still stop the spinner.
    loadPage.mockResolvedValueOnce(page([msg(6), msg(7)]));
    act(() => result.current.loadOlder());
    await act(async () => {
      resolveJump(page([msg(1), msg(2)]));
    });

    expect(result.current.search.isJumping).toBe(false);
  });

  // ---- detached window: paging forward and the way back (FINDING 3) -------

  /** Search-jump into the past, leaving the window detached from the tail. */
  const jumpIntoThePast = async (
    around: ConversationThreadPage = page([msg(1), msg(2), msg(3)], { has_more_newer: true }),
  ) => {
    searchMessages.mockResolvedValue(matches);
    loadPage.mockResolvedValueOnce(around);
    const rendered = setup();
    act(() => rendered.result.current.search.openSearch());
    act(() => rendered.result.current.search.setQuery('needle'));
    await waitFor(() => expect(rendered.result.current.search.matchCount).toBe(2));
    act(() => rendered.result.current.search.next());
    await waitFor(() => expect(rendered.result.current.isDetached).toBe(true));
    return rendered;
  };

  it('pages forward from a detached window with the newest loaded id', async () => {
    const { result } = await jumpIntoThePast();
    expect(result.current.hasMoreNewer).toBe(true);

    loadPage.mockResolvedValueOnce(
      page([msg(4), msg(5)], { has_more_older: true, has_more_newer: true }),
    );
    act(() => result.current.loadNewer());

    await waitFor(() => expect(result.current.isLoadingNewer).toBe(false));
    expect(loadPage).toHaveBeenLastCalledWith({ after: String(BASE_US + 3_000_000), limit: 50 });
    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 1_000_000,
      BASE_US + 2_000_000,
      BASE_US + 3_000_000,
      BASE_US + 4_000_000,
      BASE_US + 5_000_000,
    ]);
    // Still detached: the live tail is NOT merged until we have caught up.
    expect(result.current.isDetached).toBe(true);
  });

  it('rejoins the live tail once a forward page reports nothing newer', async () => {
    const { result } = await jumpIntoThePast();

    loadPage.mockResolvedValueOnce(
      page([msg(4), msg(5)], { has_more_older: true, has_more_newer: false }),
    );
    act(() => result.current.loadNewer());

    await waitFor(() => expect(result.current.isDetached).toBe(false));
    expect(result.current.hasMoreNewer).toBe(false);
    // Everything paged through is kept, and the live window is merged back in.
    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 1_000_000,
      BASE_US + 2_000_000,
      BASE_US + 3_000_000,
      BASE_US + 4_000_000,
      BASE_US + 5_000_000,
      BASE_US + 8_000_000,
      BASE_US + 9_000_000,
    ]);
  });

  it('counts the live messages the detached reader cannot see', async () => {
    const { result, rerender } = await jumpIntoThePast();
    expect(result.current.newerUnseenCount).toBe(2);

    rerender({ liveItems: [msg(8), msg(9), msg(10)] });
    expect(result.current.newerUnseenCount).toBe(3);
  });

  it('jump to latest puts the reader back on the live tail', async () => {
    const { result } = await jumpIntoThePast();

    act(() => result.current.jumpToLatest());

    expect(result.current.isDetached).toBe(false);
    expect(result.current.newerUnseenCount).toBe(0);
    expect(result.current.search.activeMessageId).toBeNull();
    expect(result.current.items.map((m) => m.messageId)).toEqual([
      BASE_US + 8_000_000,
      BASE_US + 9_000_000,
    ]);
    // The search bar stays open with its matches; only the cursor is dropped.
    expect(result.current.search.open).toBe(true);
    expect(result.current.search.matchCount).toBe(2);
  });

  it('does not re-fetch a jump whose page never contained the anchor', async () => {
    // FINDING 6: the around page can come back without the match (a purged or
    // out-of-scope message). Keying the bail on "is it loaded" refetched on
    // every poll tick, forever.
    searchMessages.mockResolvedValue(matches);
    loadPage.mockResolvedValue(page([msg(4), msg(5)]));
    const { result, rerender } = setup();

    act(() => result.current.search.openSearch());
    act(() => result.current.search.setQuery('needle'));
    await waitFor(() => expect(result.current.search.matchCount).toBe(2));
    act(() => result.current.search.next());
    await waitFor(() => expect(result.current.search.isJumping).toBe(false));
    expect(loadPage).toHaveBeenCalledTimes(1);

    rerender({ liveItems: [msg(8), msg(9), msg(10)] });
    rerender({ liveItems: [msg(8), msg(9), msg(10), msg(11)] });

    expect(loadPage).toHaveBeenCalledTimes(1);
  });

  // AC-N6: the drawer's quoted enquiry drives the same jump mechanism a search
  // match does, through this hook rather than a second implementation.
  describe('jumpToMessage', () => {
    it('an already-loaded message only bumps the focus target, no fetch', () => {
      const { result } = setup();

      act(() => result.current.jumpToMessage(BASE_US + 8_000_000));

      expect(loadPage).not.toHaveBeenCalled();
      expect(result.current.focusMessageId).toBe(String(BASE_US + 8_000_000));
      expect(result.current.focusNonce).toBe(1);
    });

    it('re-asking for the SAME message bumps the nonce again (scroll back twice)', () => {
      const { result } = setup();

      act(() => result.current.jumpToMessage(BASE_US + 8_000_000));
      act(() => result.current.jumpToMessage(BASE_US + 8_000_000));

      expect(result.current.focusNonce).toBe(2);
      expect(loadPage).not.toHaveBeenCalled();
    });

    it('a message outside the window loads the page around it and replaces the window', async () => {
      loadPage.mockResolvedValue(
        page([msg(2), msg(3), msg(4)], { has_more_older: true, has_more_newer: true }),
      );
      const { result } = setup();

      act(() => result.current.jumpToMessage(String(BASE_US + 3_000_000)));

      expect(result.current.isJumpingToMessage).toBe(true);
      await waitFor(() => expect(result.current.isJumpingToMessage).toBe(false));

      expect(loadPage).toHaveBeenCalledWith({
        around: String(BASE_US + 3_000_000),
        limit: 50,
      });
      // Window REPLACED (detached), not spliced - no hole in the middle.
      expect(result.current.items.map((m) => m.messageId)).toEqual([
        BASE_US + 2_000_000,
        BASE_US + 3_000_000,
        BASE_US + 4_000_000,
      ]);
      expect(result.current.isDetached).toBe(true);
      expect(result.current.focusMessageId).toBe(String(BASE_US + 3_000_000));
    });

    it('surfaces a failed around-page instead of leaving a dead control', async () => {
      loadPage.mockRejectedValue(new Error('Could not open that message.'));
      const { result } = setup();

      act(() => result.current.jumpToMessage('999'));

      await waitFor(() => expect(result.current.error).toBe('Could not open that message.'));
      expect(result.current.isJumpingToMessage).toBe(false);
    });

    it('ignores an empty target', () => {
      const { result } = setup();
      act(() => result.current.jumpToMessage(null));
      act(() => result.current.jumpToMessage(''));
      expect(result.current.focusNonce).toBe(0);
      expect(loadPage).not.toHaveBeenCalled();
    });
  });

  it('holds nothing when disabled', () => {
    const { result } = renderHook(() =>
      useConversationThread({
        liveItems: [],
        loadPage,
        searchMessages,
        enabled: false,
      }),
    );
    act(() => result.current.loadOlder());
    expect(loadPage).not.toHaveBeenCalled();
    expect(result.current.hasMoreOlder).toBe(false);
  });
});
