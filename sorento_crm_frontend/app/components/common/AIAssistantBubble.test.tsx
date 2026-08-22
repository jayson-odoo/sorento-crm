import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

/**
 * UAC AC-N5(c): the global assistant launcher is a slim edge tab pinned to the
 * bottom-right SCREEN edge, not a round FAB floating over the page. The FAB sat
 * at z-[120] - above every Sheet (z-50) - so it covered a drawer's bottom
 * controls. What is pinned here is the geometry and the stacking, at both
 * widths, plus that opening/closing still works.
 *
 * UPDATED 2026-08-18: the tab collapses to the side. Collapsed is a 32px-wide
 * VERTICAL handle (the horizontal pill was ~130px wide and sat on table rows),
 * the panel carries an explicit collapse control, and the choice is persisted so
 * it survives navigation and reload - collapsed for a first-time user.
 */
const hasPermission = vi.fn(() => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPermission(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/aiAssistantChatApi', () => ({
  fetchAIAssistantGreeting: vi.fn(async () => ({ greeting: 'Hi' })),
  listAIAssistantConversations: vi.fn(async () => []),
  loadConversation: vi.fn(async () => ({ messages: [] })),
  sendAIAssistantMessage: vi.fn(async () => ({ messages: [] })),
}));

vi.mock('@/lib/aiPageSnapshot', () => ({
  getPageSnapshot: () => null,
}));

import AIAssistantBubble from './AIAssistantBubble';

const OPEN_STORAGE_KEY = 'sorento.ai.bubbleOpen';

function handle() {
  return screen.getByTestId('ai-assistant-tab');
}

function collapseButton() {
  return screen.getByTestId('ai-assistant-collapse');
}

describe('AIAssistantBubble edge-tab launcher (AC-N5c)', () => {
  beforeEach(() => {
    hasPermission.mockReturnValue(true);
    window.localStorage.clear();
  });

  it('renders nothing without the assistant permission', () => {
    hasPermission.mockReturnValue(false);
    const { container } = render(<AIAssistantBubble />);
    expect(container.firstChild).toBeNull();
  });

  it('anchors to the bottom-right screen edge under any open sheet', () => {
    render(<AIAssistantBubble />);
    const root = document.querySelector('[data-ai-assistant-root]');
    const rootClass = root?.getAttribute('class') ?? '';
    expect(rootClass).toContain('fixed');
    expect(rootClass).toContain('end-0');
    expect(rootClass).toContain('bottom-6');
    // Above header (z-10) / sidebar (z-20), below Sheet + Dialog (z-50).
    expect(rootClass).toContain('z-40');
    expect(rootClass).not.toContain('z-[120]');
  });

  it('is a slim 32px vertical handle hugging the edge, not a wide pill or a FAB', () => {
    render(<AIAssistantBubble />);
    const cls = handle().getAttribute('class') ?? '';
    expect(cls).toContain('w-8');
    expect(cls).toContain('flex-col');
    expect(cls).toContain('rounded-s-lg');
    expect(cls).not.toContain('rounded-full');
  });

  it('rotates the label into the handle from sm up and shows the icon alone at phone width', () => {
    render(<AIAssistantBubble />);
    const label = screen.getByText('AI assistant');
    const cls = label.getAttribute('class') ?? '';
    // 375px: `hidden`. 1280px: `sm:inline`, running down the handle.
    expect(cls).toContain('hidden');
    expect(cls).toContain('sm:inline');
    expect(cls).toContain('[writing-mode:vertical-rl]');
  });
});

describe('AIAssistantBubble collapse to the side', () => {
  beforeEach(() => {
    hasPermission.mockReturnValue(true);
    window.localStorage.clear();
  });

  it('is collapsed for a first-time user: handle only, no panel', () => {
    render(<AIAssistantBubble />);
    expect(handle().getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByTestId('ai-assistant-panel')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'AI assistant' })).toBeNull();
  });

  it('expands on click, replacing the handle with the panel', () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());

    expect(screen.getByTestId('ai-assistant-panel')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'AI assistant' })).toBeDefined();
    // The handle unmounts while expanded, so the two can never overlap.
    expect(screen.queryByTestId('ai-assistant-tab')).toBeNull();
    expect(collapseButton().getAttribute('aria-expanded')).toBe('true');
  });

  it('collapses again from the panel control, returning the handle', () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());
    fireEvent.click(collapseButton());

    expect(screen.queryByTestId('ai-assistant-panel')).toBeNull();
    expect(handle().getAttribute('aria-expanded')).toBe('false');
  });

  it('persists expanding and collapsing to localStorage', () => {
    render(<AIAssistantBubble />);
    expect(window.localStorage.getItem(OPEN_STORAGE_KEY)).toBeNull();

    fireEvent.click(handle());
    expect(window.localStorage.getItem(OPEN_STORAGE_KEY)).toBe('1');

    fireEvent.click(collapseButton());
    expect(window.localStorage.getItem(OPEN_STORAGE_KEY)).toBe('0');
  });

  it('restores the expanded panel from localStorage', () => {
    window.localStorage.setItem(OPEN_STORAGE_KEY, '1');
    render(<AIAssistantBubble />);

    expect(screen.getByTestId('ai-assistant-panel')).toBeDefined();
    expect(screen.queryByTestId('ai-assistant-tab')).toBeNull();
  });

  it('stays collapsed when localStorage says collapsed', () => {
    window.localStorage.setItem(OPEN_STORAGE_KEY, '0');
    render(<AIAssistantBubble />);

    expect(screen.queryByTestId('ai-assistant-panel')).toBeNull();
    expect(handle().getAttribute('aria-expanded')).toBe('false');
  });

  it('moves focus with the toggle so a keyboard user is never dropped on the body', () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());
    expect(document.activeElement).toBe(screen.getByTestId('ai-assistant-panel'));

    fireEvent.click(collapseButton());
    expect(document.activeElement).toBe(handle());
  });
});
