/**
 * UI v2 phase 0, slice S4 (red first). UAC E-4 (playbook P16).
 *
 * EXPORT CONTRACT (the module does not exist yet; the coder implements exactly this):
 *   components/v2/shell/SystemBanner.tsx : SystemBanner()   // no props: it is the one banner host
 *     Sources, read inside the component:
 *       - impersonation : `useImpersonation()` from '@/hooks/useImpersonation' -> { session, stop, stopping };
 *                         active when `session` is non-null; message contains the target name; ONE text button
 *                         "Exit impersonation" that calls `stop()`.
 *       - offline       : `navigator.onLine === false` at mount, then the window 'offline' / 'online' events;
 *                         message matches /offline/i; no button.
 *     Urgency order (most urgent first): offline, then impersonation.
 *     Rendering: nothing when no source is active. Otherwise ONE bar
 *       <div role="status" data-testid="system-banner" data-tone="warn"> (both sources are tone "warn"),
 *       full width (class list has `w-full` or `inset-x-0`), containing
 *       <span data-slot="system-banner-message"> that is `truncate` (one line) on desktop and `line-clamp-2`
 *       (two lines) at 720 px and below.
 *     At most ONE text button in the bar. A still-true state has NO close/dismiss button.
 *     With 2 active sources the bar shows the most urgent one with the text "1 of 2" and two icon buttons
 *       aria-label "Previous banner" / "Next banner" (these are not text buttons); Next shows "2 of 2" and the other
 *       source's message.
 *     Height: while a bar is shown, sets the CSS custom property `--system-banner-height` on <html> to its
 *       offsetHeight in px; removed when no bar is shown or on unmount. (The topbar and sidebar offset by it.)
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

const stop = vi.fn();
let session: null | { sessionId: string; startedAt: string; targetUser: { id: string; name: string; email: string } } = null;
vi.mock('@/hooks/useImpersonation', () => ({
  useImpersonation: () => ({ session, stop, stopping: false }),
}));
vi.mock('@/services/contactImpersonationService', () => ({ stopContactImpersonation: vi.fn() }));
vi.mock('next/link', () => ({
  default: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) => (
    <a href={href} className={className}>{children}</a>
  ),
}));

import { SystemBanner } from './SystemBanner';

function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width });
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => {
      const max = /max-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
      const min = /min-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
      const matches = max || min ? (max ? width <= Number(max[1]) : true) && (min ? width >= Number(min[1]) : true) : false;
      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      };
    },
  });
}

function setOnline(online: boolean) {
  Object.defineProperty(window.navigator, 'onLine', { configurable: true, value: online });
}

const IMPERSONATING = {
  sessionId: 's1',
  startedAt: '2026-11-12T00:00:00Z',
  targetUser: { id: 'u1', name: 'Test Salesperson A', email: 'a@x.test' },
};

/** Text buttons: buttons that show words. Icon-only buttons carry just an aria-label. */
function textButtons(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll('button')).filter((b) => (b.textContent ?? '').trim() !== '');
}

beforeEach(() => {
  session = null;
  stop.mockReset();
  setOnline(true);
  setViewport(1280);
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 36 });
});
afterEach(() => {
  cleanup();
  document.documentElement.style.removeProperty('--system-banner-height');
});

describe('SystemBanner (E-4)', () => {
  it('renders nothing when no source is active and sets no height', () => {
    render(<SystemBanner />);
    expect(screen.queryByTestId('system-banner')).toBeNull();
    expect(document.documentElement.style.getPropertyValue('--system-banner-height')).toBe('');
  });

  it('impersonation shows ONE full-width warn bar, one text button, no close', () => {
    session = IMPERSONATING;
    render(<SystemBanner />);
    const bar = screen.getByTestId('system-banner');
    expect(bar).toHaveAttribute('role', 'status');
    expect(bar).toHaveAttribute('data-tone', 'warn');
    expect(bar.className).toMatch(/\b(w-full|inset-x-0)\b/);
    expect(bar).toHaveTextContent('Test Salesperson A');
    expect(textButtons(bar)).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Exit impersonation' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /close|dismiss|hide/i })).toBeNull();
    expect(screen.getAllByTestId('system-banner')).toHaveLength(1);
  });

  it('the single button runs the exit', () => {
    session = IMPERSONATING;
    render(<SystemBanner />);
    fireEvent.click(screen.getByRole('button', { name: 'Exit impersonation' }));
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it('offline shows a warn bar with no button, appearing and leaving with the connection', () => {
    render(<SystemBanner />);
    expect(screen.queryByTestId('system-banner')).toBeNull();
    setOnline(false);
    act(() => {
      window.dispatchEvent(new Event('offline'));
    });
    const bar = screen.getByTestId('system-banner');
    expect(bar).toHaveAttribute('data-tone', 'warn');
    expect(bar).toHaveTextContent(/offline/i);
    expect(textButtons(bar)).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /close|dismiss/i })).toBeNull();

    setOnline(true);
    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    expect(screen.queryByTestId('system-banner')).toBeNull();
  });

  it('already offline at mount shows the bar at once', () => {
    setOnline(false);
    render(<SystemBanner />);
    expect(screen.getByTestId('system-banner')).toHaveTextContent(/offline/i);
  });

  it('two sources show the most urgent (offline) with "1 of 2" and step with Next', () => {
    session = IMPERSONATING;
    setOnline(false);
    render(<SystemBanner />);
    const bar = screen.getByTestId('system-banner');
    expect(screen.getAllByTestId('system-banner')).toHaveLength(1);
    expect(bar).toHaveTextContent(/offline/i);
    expect(bar).toHaveTextContent('1 of 2');
    expect(bar).not.toHaveTextContent('Test Salesperson A');
    expect(textButtons(bar).length).toBeLessThanOrEqual(1);

    fireEvent.click(screen.getByRole('button', { name: 'Next banner' }));
    expect(screen.getByTestId('system-banner')).toHaveTextContent('2 of 2');
    expect(screen.getByTestId('system-banner')).toHaveTextContent('Test Salesperson A');
    expect(screen.getByRole('button', { name: 'Exit impersonation' })).toBeInTheDocument();
    expect(textButtons(screen.getByTestId('system-banner'))).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Previous banner' }));
    expect(screen.getByTestId('system-banner')).toHaveTextContent('1 of 2');
  });

  it('one source shows no counter', () => {
    session = IMPERSONATING;
    render(<SystemBanner />);
    expect(screen.getByTestId('system-banner')).not.toHaveTextContent(/\d of \d/);
    expect(screen.queryByRole('button', { name: /next banner|previous banner/i })).toBeNull();
  });

  it('message is one line on desktop and two lines on a phone', () => {
    session = IMPERSONATING;
    render(<SystemBanner />);
    const desktop = document.querySelector('[data-slot="system-banner-message"]') as HTMLElement;
    expect(desktop.className).toMatch(/\btruncate\b/);
    expect(desktop.className).not.toMatch(/line-clamp-2/);
    cleanup();

    setViewport(360);
    render(<SystemBanner />);
    const phone = document.querySelector('[data-slot="system-banner-message"]') as HTMLElement;
    expect(phone.className).toMatch(/\bline-clamp-2\b/);
  });

  it('publishes its height on <html> while shown and removes it after', () => {
    session = IMPERSONATING;
    const { unmount } = render(<SystemBanner />);
    expect(document.documentElement.style.getPropertyValue('--system-banner-height')).toBe('36px');
    unmount();
    expect(document.documentElement.style.getPropertyValue('--system-banner-height')).toBe('');
  });
});
