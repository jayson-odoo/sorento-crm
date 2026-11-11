/**
 * CERT-TAB-FOLLOWUPS item 3: the one shared unsaved-changes guard (crew ruling 11 Nov 2026,
 * option b). While `dirty`, every way out of the page asks first:
 *   - a same-site link click (back link, breadcrumb, sidebar, another record),
 *   - the browser's Back (a history entry kept on top of the page),
 *   - a refresh or closing the tab (the browser's own `beforeunload` prompt).
 * Answered by one AlertDialog: "Leave with unsaved changes?" with Keep editing / Leave without saving.
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.fn();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace, back: vi.fn() }),
}));

import { useUnsavedChangesGuard } from './useUnsavedChangesGuard';

function Page({ dirty }: { dirty: boolean }) {
  const dialog = useUnsavedChangesGuard(dirty, { fallbackHref: '/the/list' });
  return (
    <div>
      <a href="/elsewhere/page">Sidebar link</a>
      <a href="#section">Same page anchor</a>
      <a href="/elsewhere/new-tab" target="_blank" rel="noreferrer">
        New tab link
      </a>
      <a href="https://example.com/out">Other site</a>
      {dialog}
    </div>
  );
}

/** A click that a real <a> would turn into a navigation unless something prevents it. */
function clickLink(name: string, init: MouseEventInit = {}) {
  const link = screen.getByText(name);
  const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init });
  act(() => {
    link.dispatchEvent(event);
  });
  return event;
}

function beforeUnload() {
  const event = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(event);
  return event;
}

const dialogTitle = () => screen.queryByText('Leave with unsaved changes?');

beforeEach(() => {
  push.mockReset();
  replace.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('useUnsavedChangesGuard', () => {
  it('lets every exit through when nothing is unsaved', () => {
    render(<Page dirty={false} />);
    expect(clickLink('Sidebar link').defaultPrevented).toBe(false);
    expect(beforeUnload().defaultPrevented).toBe(false);
    expect(dialogTitle()).toBeNull();
  });

  it('asks before a same-site link leaves, and Keep editing stays', async () => {
    render(<Page dirty />);
    expect(clickLink('Sidebar link').defaultPrevented).toBe(true);
    expect(dialogTitle()).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    // The dialog animates out.
    await waitFor(() => expect(dialogTitle()).toBeNull());
    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it('Leave without saving goes where the link pointed', () => {
    render(<Page dirty />);
    clickLink('Sidebar link');
    fireEvent.click(screen.getByRole('button', { name: 'Leave without saving' }));
    const went = [...push.mock.calls, ...replace.mock.calls].map((c) => c[0]);
    expect(went).toEqual(['/elsewhere/page']);
  });

  it('leaves new-tab clicks, same-page anchors and other sites alone', () => {
    render(<Page dirty />);
    expect(clickLink('Sidebar link', { ctrlKey: true }).defaultPrevented).toBe(false);
    expect(clickLink('Sidebar link', { metaKey: true }).defaultPrevented).toBe(false);
    expect(clickLink('Same page anchor').defaultPrevented).toBe(false);
    expect(clickLink('New tab link').defaultPrevented).toBe(false);
    expect(clickLink('Other site').defaultPrevented).toBe(false);
    expect(dialogTitle()).toBeNull();
  });

  it('arms the browser leave prompt for a refresh or a closed tab', () => {
    render(<Page dirty />);
    expect(beforeUnload().defaultPrevented).toBe(true);
  });

  it('keeps a history entry on top so the browser Back asks first', () => {
    const pushState = vi.spyOn(window.history, 'pushState');
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    render(<Page dirty />);
    expect(pushState).toHaveBeenCalledTimes(1);
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
    });
    expect(dialogTitle()).toBeInTheDocument();
    // Keep editing puts the entry back, so the next Back asks again.
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    expect(pushState).toHaveBeenCalledTimes(2);
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
    });
    fireEvent.click(screen.getByRole('button', { name: 'Leave without saving' }));
    expect(back).toHaveBeenCalledTimes(1);
  });

  it('gives the history entry back once the changes are saved, so Back needs one press', () => {
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    const view = render(<Page dirty />);
    view.rerender(<Page dirty={false} />);
    expect(back).toHaveBeenCalledTimes(1);
    // That Back is the guard's own: it opens no dialog.
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
    });
    expect(dialogTitle()).toBeNull();
    expect(beforeUnload().defaultPrevented).toBe(false);
  });

  it('Leave after Back goes to the fallback page when there is no earlier page (opened in a new tab)', async () => {
    // history.back() goes nowhere: the tab has no page before this one.
    vi.spyOn(window.history, 'back').mockImplementation(() => {});
    render(<Page dirty />);
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
    });
    fireEvent.click(screen.getByRole('button', { name: 'Leave without saving' }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/the/list'));
  });
});
