import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

/**
 * UAC AC-N5(c): the global assistant launcher is a slim edge tab pinned to the
 * bottom-right SCREEN edge, not a round FAB floating over the page. The FAB sat
 * at z-[120] - above every Sheet (z-50) - so it covered a drawer's bottom
 * controls. What is pinned here is the geometry and the stacking, at both
 * widths, plus that opening/closing still works.
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

function tab() {
  return screen.getByTestId('ai-assistant-tab');
}

describe('AIAssistantBubble edge-tab launcher (AC-N5c)', () => {
  beforeEach(() => {
    hasPermission.mockReturnValue(true);
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

  it('is a 40px tall tab hugging the edge, not a round FAB', () => {
    render(<AIAssistantBubble />);
    const cls = tab().getAttribute('class') ?? '';
    expect(cls).toContain('h-10');
    expect(cls).toContain('rounded-s-full');
    expect(cls).not.toContain('rounded-full');
  });

  it('shows the label from sm up and the icon alone at phone width', () => {
    render(<AIAssistantBubble />);
    const label = screen.getByText('AI assistant');
    const cls = label.getAttribute('class') ?? '';
    // 375px: `hidden`. 1280px: `sm:inline`.
    expect(cls).toContain('hidden');
    expect(cls).toContain('sm:inline');
  });

  it('toggles the assistant panel open and closed', () => {
    render(<AIAssistantBubble />);
    expect(tab().getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('heading', { name: 'AI assistant' })).toBeNull();

    fireEvent.click(tab());
    expect(tab().getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('heading', { name: 'AI assistant' })).toBeDefined();

    fireEvent.click(tab());
    expect(tab().getAttribute('aria-expanded')).toBe('false');
  });
});
