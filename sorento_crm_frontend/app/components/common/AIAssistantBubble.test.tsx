import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

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

  it('expands on click, replacing the handle with the panel', async () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());

    expect(screen.getByTestId('ai-assistant-panel')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'AI assistant' })).toBeDefined();
    // The handle now fades out over --duration-fast (M3-07) rather than
    // unmounting on the same tick, so it stays mounted for its own exit -
    // it still unmounts once that exit completes, and the two never overlap.
    await waitFor(() => expect(screen.queryByTestId('ai-assistant-tab')).toBeNull());
    expect(collapseButton().getAttribute('aria-expanded')).toBe('true');
  });

  it('collapses again from the panel control, returning the handle', async () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());
    fireEvent.click(collapseButton());

    // The panel now materialises/dematerialises on the shared spring (S8-05),
    // so it stays mounted for its exit animation rather than vanishing on the
    // same tick the control is clicked.
    await waitFor(() => expect(screen.queryByTestId('ai-assistant-panel')).toBeNull());
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

  it('restores the expanded panel from localStorage', async () => {
    window.localStorage.setItem(OPEN_STORAGE_KEY, '1');
    render(<AIAssistantBubble />);

    // `open` starts false and flips true from an effect reading localStorage,
    // so the handle briefly mounts before exiting (M3-07's fade) - same
    // "expands" path as a click, just effect-driven instead of user-driven.
    expect(screen.getByTestId('ai-assistant-panel')).toBeDefined();
    await waitFor(() => expect(screen.queryByTestId('ai-assistant-tab')).toBeNull());
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

describe('AIAssistantBubble resize (M3-07)', () => {
  beforeEach(() => {
    hasPermission.mockReturnValue(true);
    window.localStorage.clear();
  });

  it('does not re-render on pointermove, only once on pointerup', () => {
    const onRender = vi.fn();
    render(
      <React.Profiler id="ai-bubble" onRender={onRender}>
        <AIAssistantBubble />
      </React.Profiler>,
    );
    fireEvent.click(handle());
    const corner = screen.getByTestId('ai-assistant-resize-corner');
    onRender.mockClear();

    fireEvent.pointerDown(corner, { clientX: 100, clientY: 100, pointerId: 1 });
    // pointerdown only arms local listeners - no state write, so no render.
    expect(onRender).not.toHaveBeenCalled();

    fireEvent.pointerMove(corner, { clientX: 90, clientY: 90, pointerId: 1 });
    fireEvent.pointerMove(corner, { clientX: 70, clientY: 60, pointerId: 1 });
    fireEvent.pointerMove(corner, { clientX: 40, clientY: 30, pointerId: 1 });
    // Every move so far wrote straight to the panel's own DOM style, rAF-
    // throttled - none of it went through React state.
    expect(onRender).not.toHaveBeenCalled();

    fireEvent.pointerUp(corner, { clientX: 40, clientY: 30, pointerId: 1 });
    // The one point a re-render is needed - to persist the final size.
    expect(onRender).toHaveBeenCalledTimes(1);
  });

  it('writes the dragged size to the panel element during the move', async () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());
    const panel = screen.getByTestId('ai-assistant-panel');
    const corner = screen.getByTestId('ai-assistant-resize-corner');
    const startWidth = panel.style.width;

    fireEvent.pointerDown(corner, { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(corner, { clientX: 40, clientY: 40, pointerId: 1 });
    // The write is rAF-throttled - real timers here, so wait one real frame.
    await act(async () => {
      await new Promise((resolve) => requestAnimationFrame(resolve));
    });

    // Dragging the corner up-left grows both dimensions - written directly
    // onto the panel's style, independent of whether React has re-rendered.
    expect(panel.style.width).not.toBe(startWidth);

    fireEvent.pointerUp(corner, { clientX: 40, clientY: 40, pointerId: 1 });
  });

  it('presses rather than widening on hover, and stays a real button', () => {
    render(<AIAssistantBubble />);
    // `transition-all hover:w-9` grew the handle on hover and, because `all`
    // includes opacity, smeared the AnimatePresence exit it now has (M3-07).
    // The press is the shared class every other control uses.
    expect(handle().className).not.toContain('transition-all');
    expect(handle().className).not.toContain('hover:w-9');
    expect(handle().className).toContain('active:scale-[0.97]');
    // The exit behaviour itself (fading rather than vanishing) is covered by
    // the "expands on click" test above, which has to `waitFor` the unmount.
    expect(handle().tagName).toBe('BUTTON');
  });
});
