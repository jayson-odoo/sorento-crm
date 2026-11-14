/**
 * UI v2 phase 0, slice S4 (red first). UAC E-1, D-5 ("mounted once in AppShell"), D-6 (shell side).
 *
 * EXPORT CONTRACT (the modules do not exist yet; the coder implements exactly this):
 *   components/v2/shell/AppShell.tsx : AppShell({ children })
 *     Composes, from siblings in components/v2/shell/ (all named exports, mocked here):
 *       Sidebar        './Sidebar'        ()                    desktop sidebar built from MENU_SIDEBAR
 *       Topbar         './Topbar'         ({ onOpenNav })
 *       SystemBanner   './SystemBanner'   ()
 *       MobileNavSheet './MobileNavSheet' ({ open, onOpenChange })   the phone navigation drawer
 *       usePageView    './usePageView'    ()                    called by AppShell and nowhere else
 *     DOM: SystemBanner comes BEFORE Topbar in document order (the banner sits above the top bar); the page
 *     content is rendered inside a single <main>.
 *     Desktop (width > 720): Sidebar is rendered; MobileNavSheet is not.
 *     Phone (width <= 720):  Sidebar is not rendered; Topbar's onOpenNav opens MobileNavSheet (open=true).
 *   components/v2/shell/Sidebar.tsx builds its entries from `MENU_SIDEBAR` of '@/config/menu.config' and from no
 *     demo config (MENU_SIDEBAR_COMPACT, MENU_SIDEBAR_CUSTOM, MENU_MEGA*, MENU_ROOT are not imported).
 */
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

const lifecycle = { mounts: 0, unmounts: 0 };
const usePageViewSpy = vi.fn();
vi.mock('./usePageView', () => ({
  usePageView: () => {
    usePageViewSpy();
    // Counts instances (mounts), not renders, so a state update inside the shell cannot inflate it.
    React.useEffect(() => {
      lifecycle.mounts += 1;
      return () => {
        lifecycle.unmounts += 1;
      };
    }, []);
  },
}));
vi.mock('./Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
vi.mock('./Topbar', () => ({
  Topbar: ({ onOpenNav }: { onOpenNav?: () => void }) => (
    <header data-testid="topbar">
      <button type="button" onClick={onOpenNav}>open-nav</button>
    </header>
  ),
}));
vi.mock('./SystemBanner', () => ({ SystemBanner: () => <div data-testid="system-banner" /> }));
vi.mock('./MobileNavSheet', () => ({
  MobileNavSheet: ({ open }: { open: boolean }) => <div data-testid="mobile-nav" data-open={String(open)} />,
}));
// Parity pieces the v1 shell carries; mocked so a shell that also mounts them needs no provider tree here.
vi.mock('@/app/components/module-route-guard', () => ({
  ModuleRouteGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/app/components/common/AIAssistantBubble', () => ({ default: () => null }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { AppShell } from './AppShell';

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

const read = (rel: string) => fs.readFileSync(path.resolve(__dirname, rel), 'utf8');

beforeEach(() => {
  lifecycle.mounts = 0;
  lifecycle.unmounts = 0;
  usePageViewSpy.mockClear();
  setViewport(1280);
});
afterEach(cleanup);

describe('AppShell (E-1)', () => {
  it('at 1280 renders sidebar, banner, topbar and the page inside one <main>', () => {
    render(<AppShell><p>Page body</p></AppShell>);
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('topbar')).toBeInTheDocument();
    expect(screen.getByTestId('system-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('mobile-nav')).toBeNull();
    const mains = document.querySelectorAll('main');
    expect(mains).toHaveLength(1);
    expect(mains[0]).toContainElement(screen.getByText('Page body'));
  });

  it('the system banner sits above the top bar', () => {
    render(<AppShell><p>Page body</p></AppShell>);
    const banner = screen.getByTestId('system-banner');
    const topbar = screen.getByTestId('topbar');
    expect(banner.compareDocumentPosition(topbar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('on a phone the sidebar goes away and the top bar opens the navigation sheet', () => {
    setViewport(360);
    render(<AppShell><p>Page body</p></AppShell>);
    expect(screen.queryByTestId('sidebar')).toBeNull();
    expect(screen.getByTestId('mobile-nav')).toHaveAttribute('data-open', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'open-nav' }));
    expect(screen.getByTestId('mobile-nav')).toHaveAttribute('data-open', 'true');
  });
});

describe('AppShell content column fills the row (crew-pass 6879537499)', () => {
  // <body> is a flex row (app/layout.tsx). A column without grow/w-full shrinks to its content, so a
  // record with narrow cards (OI General tab) left a 162 px empty strip at 1280 and the top bar jumped.
  for (const width of [1280, 360]) {
    it(`at ${width} the column holding the top bar and <main> grows to the full width`, () => {
      setViewport(width);
      render(<AppShell><p>narrow content</p></AppShell>);
      const column = screen.getByTestId('topbar').parentElement as HTMLElement;
      expect(column).toContainElement(document.querySelector('main'));
      const cls = column.className.split(/\s+/);
      expect(cls).toContain('w-full');
      expect(cls).toContain('grow');
      expect(cls).toContain('min-w-0');
    });
  }
});

describe('usePageView is mounted once, in AppShell (D-5)', () => {
  it('exactly one instance is mounted, and it stays one across shell state changes', () => {
    setViewport(360);
    render(<AppShell><p>Page body</p></AppShell>);
    expect(lifecycle.mounts).toBe(1);
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'open-nav' }));
    });
    expect(lifecycle.mounts).toBe(1);
    expect(lifecycle.unmounts).toBe(0);
  });

  it('AppShell.tsx calls usePageView exactly once in its source', () => {
    const src = read('AppShell.tsx');
    const calls = src.match(/\busePageView\s*\(/g) ?? [];
    expect(calls).toHaveLength(1);
  });

  it('no other file in components/v2/shell calls it', () => {
    const others = fs
      .readdirSync(__dirname)
      .filter((f) => /\.tsx?$/.test(f) && !/\.test\./.test(f) && f !== 'AppShell.tsx' && f !== 'usePageView.ts');
    for (const f of others) expect(read(f), f).not.toMatch(/\busePageView\s*\(/);
  });
});

describe('Sidebar config (E-1)', () => {
  it('is built from MENU_SIDEBAR and no demo menu config', () => {
    const src = read('Sidebar.tsx');
    expect(src).toMatch(/MENU_SIDEBAR\b/);
    expect(src).toMatch(/from ['"]@\/config\/menu\.config['"]/);
    expect(src).not.toMatch(/MENU_SIDEBAR_COMPACT|MENU_SIDEBAR_CUSTOM|MENU_MEGA|MENU_ROOT|MENU_HELP/);
  });
});
