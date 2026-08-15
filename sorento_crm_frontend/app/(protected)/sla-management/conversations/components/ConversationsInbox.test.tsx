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

/** The `?contact=` deep link a mention notification lands on. */
let searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}));

/** The row the list "loads" - what a `?contact=` placeholder upgrades to. */
const loadedRow = {
  contact_ref: '10025531',
  respond_io_id: '10025531',
  phone: '+60123456789',
  name: 'Aisyah',
  last_message_at: '2026-08-15T02:11:03',
  last_message_snippet: 'Yes please',
  last_message_direction: 'incoming' as const,
  mentioned_at: null,
  open_ticket_count: 1,
  my_open_ticket_count: 1,
  my_open_ticket_id: 't1',
};

vi.mock('./ConversationListPane', () => ({
  default: ({
    tab,
    onTabChange,
    selectedRef,
    onSelect,
    onRowsLoaded,
    className,
  }: {
    tab: string;
    onTabChange: (t: string) => void;
    selectedRef: string | null;
    onSelect: (item: unknown) => void;
    onRowsLoaded?: (items: unknown[]) => void;
    className?: string;
  }) => (
    <div data-testid="list-pane" data-class={className} data-tab={tab} data-selected={selectedRef ?? ''}>
      <button type="button" data-testid="pick-contact" onClick={() => onSelect(loadedRow)}>
        pick
      </button>
      <button type="button" data-testid="switch-tab" onClick={() => onTabChange('all')}>
        all
      </button>
      <button
        type="button"
        data-testid="rows-loaded"
        onClick={() => onRowsLoaded?.([loadedRow])}
      >
        rows
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
    contact: { contact_ref: string; name: string | null } | null;
    canReply: boolean;
    onBack?: () => void;
    className?: string;
  }) => (
    <div
      data-testid="thread-pane"
      data-class={className}
      data-contact={contact?.contact_ref ?? ''}
      data-contact-name={contact?.name ?? ''}
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
  searchParams = new URLSearchParams();
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

  // ---- ?contact= deep link (the mention notification lands here) ----------

  it('opens the named contact straight away and lands on Mentioned', () => {
    searchParams = new URLSearchParams('contact=10025531');
    render(<ConversationsInbox />);

    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact', '10025531');
    // The mention that produced the link is newest-first on this tab, so the
    // row is on its first page and the placeholder can upgrade.
    expect(screen.getByTestId('list-pane')).toHaveAttribute('data-tab', 'mentioned');
  });

  it('upgrades the deep-link placeholder to the real row once the list has it', () => {
    searchParams = new URLSearchParams('contact=10025531');
    render(<ConversationsInbox />);
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact-name', '');

    fireEvent.click(screen.getByTestId('rows-loaded'));

    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact-name', 'Aisyah');
  });

  it('never replaces a row the user picked', () => {
    render(<ConversationsInbox />);
    fireEvent.click(screen.getByTestId('pick-contact'));
    fireEvent.click(screen.getByTestId('rows-loaded'));
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact', '10025531');
  });

  it('an unknown ?contact= still opens the thread, it just never upgrades', () => {
    searchParams = new URLSearchParams('contact=99999999');
    render(<ConversationsInbox />);
    fireEvent.click(screen.getByTestId('rows-loaded'));

    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact', '99999999');
    expect(screen.getByTestId('thread-pane')).toHaveAttribute('data-contact-name', '');
  });
});
