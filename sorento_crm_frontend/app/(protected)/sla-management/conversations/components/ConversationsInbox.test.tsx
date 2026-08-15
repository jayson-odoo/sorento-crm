import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

/**
 * The two-pane shell (UAC AC-N1 / AC-N2). Panes are stubbed: this suite is
 * about how they compose - the reply permission reaching the composer, the
 * selection round trip, and the 375px stack (list first, thread taking over
 * with a way back) expressed as responsive classes rather than a viewport hook.
 */
const hasPermission = vi.fn(() => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (...a: unknown[]) => hasPermission(...(a as [])),
}));

vi.mock('./ConversationListPane', () => ({
  default: ({
    tab,
    onTabChange,
    selectedRef,
    onSelect,
    className,
  }: {
    tab: string;
    onTabChange: (t: string) => void;
    selectedRef: string | null;
    onSelect: (item: unknown) => void;
    className?: string;
  }) => (
    <div data-testid="list-pane" data-class={className} data-tab={tab} data-selected={selectedRef ?? ''}>
      <button
        type="button"
        data-testid="pick-contact"
        onClick={() => onSelect({ contact_ref: '10025531', name: 'Aisyah', my_open_ticket_id: 't1' })}
      >
        pick
      </button>
      <button type="button" data-testid="switch-tab" onClick={() => onTabChange('all')}>
        all
      </button>
    </div>
  ),
}));

vi.mock('./ConversationThreadPane', () => ({
  default: ({
    contact,
    canReply,
    onBack,
    className,
  }: {
    contact: { contact_ref: string } | null;
    canReply: boolean;
    onBack?: () => void;
    className?: string;
  }) => (
    <div
      data-testid="thread-pane"
      data-class={className}
      data-contact={contact?.contact_ref ?? ''}
      data-can-reply={String(canReply)}
    >
      <button type="button" data-testid="back" onClick={() => onBack?.()}>
        back
      </button>
    </div>
  ),
}));

import ConversationsInbox from './ConversationsInbox';

beforeEach(() => {
  hasPermission.mockReturnValue(true);
});

const classOf = (testId: string) =>
  screen.getByTestId(testId).getAttribute('data-class') ?? '';

describe('ConversationsInbox', () => {
  it('opens on Mine with no conversation selected', () => {
    render(<ConversationsInbox />);
    expect(screen.getByTestId('list-pane')).toHaveAttribute('data-tab', 'mine');
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact', '');
  });

  it('375px: the list is the page until a contact is picked, then the thread is', () => {
    render(<ConversationsInbox />);
    // Nothing picked: list visible at every width, thread desktop-only.
    expect(classOf('list-pane')).toContain('flex');
    expect(classOf('list-pane')).not.toContain('hidden');
    expect(classOf('thread-pane')).toContain('hidden lg:flex');

    fireEvent.click(screen.getByTestId('pick-contact'));

    // Picked: they swap on mobile, both stay side by side from lg up.
    expect(classOf('list-pane')).toContain('hidden lg:flex');
    expect(classOf('thread-pane')).toContain('flex');
    expect(classOf('thread-pane')).not.toContain('hidden');
  });

  it('passes the picked contact to the thread and the back control clears it', () => {
    render(<ConversationsInbox />);
    fireEvent.click(screen.getByTestId('pick-contact'));
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact', '10025531');
    expect(screen.getByTestId('list-pane')).toHaveAttribute('data-selected', '10025531');

    fireEvent.click(screen.getByTestId('back'));
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact', '');
  });

  it('switching tab drops the selection - the row may not be in the new tab', () => {
    render(<ConversationsInbox />);
    fireEvent.click(screen.getByTestId('pick-contact'));
    fireEvent.click(screen.getByTestId('switch-tab'));

    expect(screen.getByTestId('list-pane')).toHaveAttribute('data-tab', 'all');
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact', '');
  });

  it('read access does not imply reply access', () => {
    hasPermission.mockReturnValue(false);
    render(<ConversationsInbox />);
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-can-reply', 'false');
  });
});
