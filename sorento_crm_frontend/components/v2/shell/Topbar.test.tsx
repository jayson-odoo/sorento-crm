/**
 * UI v2 phase 0, slice S4 (red first). UAC E-1 (top bar part) and E-2 (playbook P6).
 *
 * EXPORT CONTRACT (the module does not exist yet; the coder implements exactly this):
 *   components/v2/shell/Topbar.tsx : Topbar({ onOpenNav }: { onOpenNav?: () => void })
 *     Imports the existing topbar parts through the `@/app/components/partials/...` path (the vitest alias only
 *     maps `@` to the repo root, so `@/partials/...` does not resolve in tests):
 *       SearchDialog   '@/app/components/partials/dialogs/search/search-dialog'  ({ trigger })
 *       CompanySwitcher '@/app/components/partials/topbar/company-switcher'      ()
 *       NotificationsSheet '@/app/components/partials/topbar/notifications-sheet' ({ trigger })
 *       UserDropdownMenu '@/app/components/partials/topbar/user-dropdown-menu'   ({ trigger })
 *     Root is <header data-testid="topbar" data-condensed="true|false"> whose class list has `h-14` (56 px) in
 *     BOTH states (the height never changes).
 *     Search: the `trigger` given to SearchDialog is a button whose accessible name matches /search/i, inside an
 *       element <div data-slot="topbar-search">. That element has class `h-9` (36 px) only while condensed; at
 *       rest on a phone it has a taller class (44 px touch target) and no `h-9`.
 *     Right-hand parts at rest: CompanySwitcher, NotificationsSheet, UserDropdownMenu all render.
 *     Condensing (phone only, width <= 720): scrolling DOWN (window.scrollY grows past 0) sets
 *       data-condensed="true"; scrolling back UP sets "false". Desktop never condenses.
 *       While condensed the three right-hand parts are replaced by ONE button aria-label "More actions"; clicking
 *       it brings the three parts back in the bar (data-condensed stays "true", the "More actions" button goes).
 *     Phone only: a button aria-label "Open navigation" that calls onOpenNav; absent above 720 px.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) => (
    <a href={href} className={className}>{children}</a>
  ),
}));
vi.mock('@/app/components/partials/dialogs/search/search-dialog', () => ({
  SearchDialog: ({ trigger }: { trigger: React.ReactNode }) => <div data-testid="search-dialog">{trigger}</div>,
}));
vi.mock('@/app/components/partials/topbar/company-switcher', () => ({
  CompanySwitcher: () => <div data-testid="company-switcher" />,
}));
vi.mock('@/app/components/partials/topbar/notifications-sheet', () => ({
  NotificationsSheet: ({ trigger }: { trigger: React.ReactNode }) => <div data-testid="notifications">{trigger}</div>,
}));
vi.mock('@/app/components/partials/topbar/user-dropdown-menu', () => ({
  UserDropdownMenu: ({ trigger }: { trigger: React.ReactNode }) => <div data-testid="user-menu">{trigger}</div>,
}));
vi.mock('@/app/components/partials/topbar/session-user-avatar', () => ({
  SessionUserAvatar: () => <span data-testid="avatar" />,
}));

import { Topbar } from './Topbar';

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

function scrollTo(y: number) {
  Object.defineProperty(window, 'scrollY', { configurable: true, writable: true, value: y });
  Object.defineProperty(window, 'pageYOffset', { configurable: true, writable: true, value: y });
  act(() => {
    window.dispatchEvent(new Event('scroll'));
  });
}

const bar = () => screen.getByTestId('topbar');
const rightParts = ['company-switcher', 'notifications', 'user-menu'];

beforeEach(() => {
  setViewport(1280);
  scrollTo(0);
});
afterEach(cleanup);

describe('Topbar at 1280 (E-1)', () => {
  it('has the search trigger, company switcher, notifications and avatar menu', () => {
    render(<Topbar />);
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument();
    for (const id of rightParts) expect(screen.getByTestId(id)).toBeInTheDocument();
  });

  it('the search trigger lives inside the existing SearchDialog (Cmd/Ctrl+K dialog)', () => {
    render(<Topbar />);
    const dialog = screen.getByTestId('search-dialog');
    expect(dialog).toContainElement(screen.getByRole('button', { name: /search/i }));
  });

  it('has no phone navigation button', () => {
    render(<Topbar onOpenNav={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Open navigation' })).toBeNull();
  });

  it('never condenses on desktop, however far the page scrolls', () => {
    render(<Topbar />);
    scrollTo(400);
    expect(bar()).toHaveAttribute('data-condensed', 'false');
    expect(screen.queryByRole('button', { name: 'More actions' })).toBeNull();
  });
});

describe('Topbar on a phone (E-2, P6)', () => {
  beforeEach(() => setViewport(360));

  it('at rest: 56 px bar, all three parts, full-height search, nav button', () => {
    const onOpenNav = vi.fn();
    render(<Topbar onOpenNav={onOpenNav} />);
    expect(bar()).toHaveAttribute('data-condensed', 'false');
    expect(bar().className).toMatch(/\bh-14\b/);
    for (const id of rightParts) expect(screen.getByTestId(id)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'More actions' })).toBeNull();
    const search = document.querySelector('[data-slot="topbar-search"]') as HTMLElement;
    expect(search.className).not.toMatch(/\bh-9\b/);
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    expect(onOpenNav).toHaveBeenCalledTimes(1);
  });

  it('scrolling down keeps the height, folds the icons into one menu button and narrows search to 36 px', () => {
    render(<Topbar />);
    scrollTo(120);
    expect(bar()).toHaveAttribute('data-condensed', 'true');
    expect(bar().className).toMatch(/\bh-14\b/);
    for (const id of rightParts) expect(screen.queryByTestId(id)).toBeNull();
    expect(screen.getAllByRole('button', { name: 'More actions' })).toHaveLength(1);
    const search = document.querySelector('[data-slot="topbar-search"]') as HTMLElement;
    expect(search.className).toMatch(/\bh-9\b/);
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument();
  });

  it('scrolling back up reverses it', () => {
    render(<Topbar />);
    scrollTo(300);
    expect(bar()).toHaveAttribute('data-condensed', 'true');
    scrollTo(100);
    expect(bar()).toHaveAttribute('data-condensed', 'false');
    for (const id of rightParts) expect(screen.getByTestId(id)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'More actions' })).toBeNull();
    const search = document.querySelector('[data-slot="topbar-search"]') as HTMLElement;
    expect(search.className).not.toMatch(/\bh-9\b/);
  });

  it('tapping More actions opens the icons back up in the bar', () => {
    render(<Topbar />);
    scrollTo(120);
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    for (const id of rightParts) expect(screen.getByTestId(id)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'More actions' })).toBeNull();
    expect(bar().className).toMatch(/\bh-14\b/);
  });
});
