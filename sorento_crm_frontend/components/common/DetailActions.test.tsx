/**
 * S3-02 and S3-07 - the record card's action group, and its parity with the
 * list row's "..." menu.
 *
 * D15 is the point: an entity declares its actions once and both surfaces render
 * that array, in that order, with Delete last and in red. A test that only
 * checked one surface would let the two drift, which is exactly the state S3 was
 * written to end (Impersonate was list-only, Delete was record-only).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { Mail, Trash2, UserCog } from 'lucide-react';

import DetailActions from './DetailActions';

// The pager has its own test; here it is only the first slot in the group.
vi.mock('./ListPager', () => ({
  default: () => <div data-testid="pager-slot" />,
}));

import { RowActionsMenu } from './RowActionsMenu';
import type { RecordAction } from './recordActions';

const impersonate = vi.fn();
const invite = vi.fn();
const remove = vi.fn();

function actionSet(): RecordAction[] {
  return [
    { key: 'user.impersonate', label: 'Impersonate user', icon: UserCog, run: impersonate },
    { key: 'user.resend_invite', label: 'Send invitation link', icon: Mail, run: invite },
    {
      key: 'user.delete',
      label: 'Trash user',
      icon: Trash2,
      kind: 'destructive',
      run: remove,
    },
  ];
}

/** Radix opens on pointerdown, not click. */
function openMenu(trigger: HTMLElement) {
  fireEvent.pointerDown(
    trigger,
    new MouseEvent('pointerdown', { bubbles: true, button: 0 }),
  );
}

function menuItemLabels(): string[] {
  return screen
    .getAllByRole('menuitem')
    .map((item) => (item.textContent || '').trim());
}

beforeEach(() => {
  cleanup();
  impersonate.mockReset();
  invite.mockReset();
  remove.mockReset();
});

describe('DetailActions', () => {
  it('S3-02: reads pager, gear, primary from left to right', () => {
    render(
      <DetailActions
        pager={{
          detailPath: '/user-management/users',
          currentId: 'u1',
          listQueryKey: () => ['users'],
          fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
        }}
        actions={actionSet()}
        primary={<button type="button">Edit user</button>}
      />,
    );

    const group = screen.getByTestId('pager-slot').parentElement as HTMLElement;
    const rendered = Array.from(group.children).map((el) =>
      el.getAttribute('data-testid') ??
      el.getAttribute('aria-label') ??
      (el.textContent || '').trim(),
    );

    expect(rendered.slice(0, 3)).toEqual(['pager-slot', 'Actions', 'Edit user']);
  });

  it('S3-02: the gear lists the secondary actions, then a separator, then Delete last in red', () => {
    render(<DetailActions actions={actionSet()} />);

    openMenu(screen.getByRole('button', { name: 'Actions' }));

    expect(menuItemLabels()).toEqual([
      'Impersonate user',
      'Send invitation link',
      'Trash user',
    ]);

    const destructive = screen.getByRole('menuitem', { name: 'Trash user' });
    expect(destructive.className).toContain('text-destructive');

    // The separator sits between the last secondary item and the destructive one.
    const menu = destructive.closest('[role="menu"]') as HTMLElement;
    const rows = Array.from(menu.children);
    const separatorIndex = rows.findIndex(
      (el) => el.getAttribute('role') === 'separator',
    );
    expect(separatorIndex).toBe(rows.indexOf(destructive) - 1);
  });

  it('S3-02: no gear is rendered when every action was filtered away by permissions', () => {
    render(<DetailActions actions={[]} primary={<button type="button">Edit user</button>} />);

    expect(screen.queryByRole('button', { name: 'Actions' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Edit user' })).toBeTruthy();
  });

  it('S3-02: an action runs the entity handler', () => {
    render(<DetailActions actions={actionSet()} />);

    openMenu(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Send invitation link' }));

    expect(invite).toHaveBeenCalledTimes(1);
  });
});

describe('RowActionsMenu', () => {
  it('S3-07: the row menu shows the same items, in the same order, as the gear', () => {
    const { unmount } = render(<DetailActions actions={actionSet()} />);
    openMenu(screen.getByRole('button', { name: 'Actions' }));
    const fromGear = menuItemLabels();
    unmount();
    cleanup();

    render(<RowActionsMenu actions={actionSet()} ariaLabel="user" />);
    openMenu(screen.getByRole('button', { name: 'user actions' }));
    const fromRow = menuItemLabels();

    expect(fromRow).toEqual(fromGear);
    expect(
      screen.getByRole('menuitem', { name: 'Trash user' }).className,
    ).toContain('text-destructive');
  });

  it('S3-07: the row menu does not open the row it sits in', () => {
    const rowClick = vi.fn();
    render(
      <div onClick={rowClick}>
        <RowActionsMenu actions={actionSet()} ariaLabel="user" />
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'user actions' }));

    expect(rowClick).not.toHaveBeenCalled();
  });

  it('S3-07: a row whose actions are all permission-filtered renders no menu', () => {
    const { container } = render(<RowActionsMenu actions={[]} ariaLabel="user" />);

    expect(within(container).queryByRole('button')).toBeNull();
  });
});
