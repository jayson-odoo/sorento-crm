/**
 * UI v2 phase 0, slice S4 (red first). UAC E-6 (playbook P7).
 *
 * EXPORT CONTRACT (the module does not exist yet; the coder implements exactly this):
 *   components/v2/PanelTabs.tsx : PanelTabs({ panels })
 *     panels: Array<{ id: string; label: string; count?: number; content: ReactNode }>
 *     The FIRST panel is the main one and the default tab.
 *   Viewport rule (720 px, read from window.matchMedia or window.innerWidth; the tests set both):
 *     width > 720  : every panel renders side by side; each is a <section aria-label={label}>; there is NO tablist.
 *     width <= 720 : browser-style tabs:
 *        - one role="tablist" holding one role="tab" per panel; the accessible name is the label, followed by
 *          the count when present ("Changes 5"); the active tab has aria-selected="true";
 *        - each tab class list contains a `rounded-t*` class (rounded tops);
 *        - one role="tabpanel" per panel, labelled by its tab. Inactive panels stay MOUNTED with the `hidden`
 *          attribute, so each keeps its own DOM, scroll position and state across switches;
 *        - each tabpanel is its own scroller: its class list contains `overflow-y-auto`.
 *     A single panel renders its content with no tablist at any width.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { PanelTabs } from './PanelTabs';

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

const PANELS = [
  { id: 'info', label: 'Quick Info', content: <div>Info body</div> },
  { id: 'changes', label: 'Changes', count: 5, content: <input aria-label="Change note" defaultValue="" /> },
];

beforeEach(() => setViewport(1280));
afterEach(cleanup);

describe('PanelTabs (E-6)', () => {
  it('above 720 px renders the panels side by side with no tablist', () => {
    render(<PanelTabs panels={PANELS} />);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.getByRole('region', { name: 'Quick Info' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Changes' })).toBeInTheDocument();
    expect(screen.getByText('Info body')).toBeVisible();
    expect(screen.getByLabelText('Change note')).toBeVisible();
  });

  it('at 721 px it is still side by side', () => {
    setViewport(721);
    render(<PanelTabs panels={PANELS} />);
    expect(screen.queryByRole('tablist')).toBeNull();
  });

  it('at 720 px and below renders browser-style tabs, the first panel selected', () => {
    setViewport(720);
    render(<PanelTabs panels={PANELS} />);
    expect(screen.getByRole('tablist')).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent?.replace(/\s+/g, ' ').trim())).toEqual(['Quick Info', 'Changes 5']);
    expect(screen.getByRole('tab', { name: 'Quick Info' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Changes 5' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByText('Info body')).toBeVisible();
  });

  it('tabs have rounded tops and each panel is its own scroller', () => {
    setViewport(360);
    render(<PanelTabs panels={PANELS} />);
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab.className).toMatch(/\brounded-t/);
    }
    const panels = screen.getAllByRole('tabpanel', { hidden: true });
    expect(panels).toHaveLength(2);
    for (const panel of panels) expect(panel.className).toMatch(/\boverflow-y-auto\b/);
  });

  it('selecting a tab shows its panel and hides the other, keeping both mounted', () => {
    setViewport(360);
    render(<PanelTabs panels={PANELS} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Changes 5' }));
    expect(screen.getByRole('tab', { name: 'Changes 5' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Quick Info' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByLabelText('Change note')).toBeVisible();
    const hiddenInfo = screen.getByText('Info body');
    expect(hiddenInfo).toBeInTheDocument();
    expect(hiddenInfo.closest('[role="tabpanel"]')).toHaveAttribute('hidden');
  });

  it('each tab keeps its own scroll and state across switches', () => {
    setViewport(360);
    render(<PanelTabs panels={PANELS} />);
    const infoPanel = screen.getByText('Info body').closest('[role="tabpanel"]') as HTMLElement;
    infoPanel.scrollTop = 120;

    fireEvent.click(screen.getByRole('tab', { name: 'Changes 5' }));
    fireEvent.change(screen.getByLabelText('Change note'), { target: { value: 'half typed' } });
    fireEvent.click(screen.getByRole('tab', { name: 'Quick Info' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Changes 5' }));

    expect(screen.getByText('Info body').closest('[role="tabpanel"]')).toBe(infoPanel);
    expect(infoPanel.scrollTop).toBe(120);
    expect(screen.getByLabelText('Change note')).toHaveValue('half typed');
  });

  it('a single panel renders with no tablist at any width', () => {
    for (const width of [1280, 360]) {
      setViewport(width);
      render(<PanelTabs panels={[PANELS[0]]} />);
      expect(screen.queryByRole('tablist')).toBeNull();
      expect(screen.getByText('Info body')).toBeVisible();
      cleanup();
    }
  });
});
