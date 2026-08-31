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
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within, act, waitFor } from '@testing-library/react';
import { Mail, Trash2, UserCog } from 'lucide-react';

import DetailActions from './DetailActions';

// The pager has its own test; here it is only the first slot in the group.
vi.mock('./ListPager', () => ({
  default: () => <div data-testid="pager-slot" />,
}));

import { RowActionsMenu } from './RowActionsMenu';
import { DetailActionsMenu } from './DetailActionsMenu';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
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

/**
 * A menu's items and separators, in document order.
 *
 * NOT `Array.from(menu.children)` - the menu's own scale/opacity spring
 * (S8-01) animates an inner div rather than the `[role="menu"]` element
 * itself (so it never fights Radix Popper's own positioning transform on that
 * same node, apple-alignment S8), which makes every row a grandchild now
 * rather than a direct child. `querySelectorAll` still returns them in
 * document order regardless of nesting depth.
 */
function menuRows(menu: HTMLElement): HTMLElement[] {
  return Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"], [role="separator"]'));
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
    const rows = menuRows(menu);
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

describe('DetailActionsMenu, children mode', () => {
  /**
   * The fifteen workflow gears pass menu items rather than a `RecordAction[]`,
   * because their secondary actions are a status graph, not a record action set.
   * They must still look like every other gear, and that cannot be left to
   * fifteen call sites remembering it.
   */
  function workflowGear() {
    return (
      <DetailActions
        gear={
          <DetailActionsMenu ariaLabel="Actions">
            <DropdownMenuItem onSelect={() => {}}>Send for approval</DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={() => {}}>
              Void
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => {}}>Export to Excel</DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={() => {}}>
              Delete
            </DropdownMenuItem>
          </DetailActionsMenu>
        }
      />
    );
  }

  it('S3-02: the destructive children go last, behind a separator the menu adds itself', () => {
    render(workflowGear());

    openMenu(screen.getByRole('button', { name: 'Actions' }));

    expect(menuItemLabels()).toEqual([
      'Send for approval',
      'Export to Excel',
      'Void',
      'Delete',
    ]);

    const menu = screen.getByRole('menu') as HTMLElement;
    const rows = menuRows(menu);
    const separators = rows.filter((el) => el.getAttribute('role') === 'separator');
    expect(separators).toHaveLength(1);
    expect(rows.indexOf(separators[0])).toBe(
      rows.indexOf(screen.getByRole('menuitem', { name: 'Void' })) - 1,
    );
  });

  it('S3-02: a gear with no destructive child gets no separator', () => {
    render(
      <DetailActions
        gear={
          <DetailActionsMenu ariaLabel="Actions">
            <DropdownMenuItem onSelect={() => {}}>Send for approval</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => {}}>Export to Excel</DropdownMenuItem>
          </DetailActionsMenu>
        }
      />,
    );

    openMenu(screen.getByRole('button', { name: 'Actions' }));

    expect(
      menuRows(screen.getByRole('menu') as HTMLElement).filter(
        (el) => el.getAttribute('role') === 'separator',
      ),
    ).toHaveLength(0);
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

describe('a confirmable action (S7-06: Copy link had zero feedback)', () => {
  /**
   * A "Copy link" item used to run `copyToClipboard` and let Radix close the
   * menu on select, same as any other item - so the confirmation the S7-05 tick
   * pattern relies on had nowhere left to render by the time anyone looked.
   * `confirmLabel` keeps the menu open long enough to show it, then closes
   * itself.
   */
  it('swaps the icon and label to the confirmation, then closes the menu on its own', async () => {
    const run = vi.fn().mockResolvedValue(true);
    const actions: RecordAction[] = [
      { key: 'record.copy_link', label: 'Copy link', run, confirmLabel: 'Copied' },
    ];
    render(<DetailActions actions={actions} />);

    openMenu(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy link' }));

    expect(run).toHaveBeenCalledTimes(1);
    // Real timers throughout: the close is animated now (S8), and motion's
    // exit resolves on rAF, which sinon's faked clock freezes - fake-timer
    // advances left the menu mounted forever. Reduced motion (vitest.setup)
    // keeps the exit instant, so only the self-close delay is really waited.
    await waitFor(() => expect(screen.getByRole('menuitem', { name: 'Copied' })).toBeInTheDocument());
    // The menu is still open - a menu that closed on select would have taken
    // this confirmation down with it before anyone read it.
    expect(screen.getByRole('menu')).toBeInTheDocument();

    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument(), { timeout: 4000 });
  });

  it('a refused write skips the tick and closes right away', async () => {
    const run = vi.fn().mockResolvedValue(false);
    const actions: RecordAction[] = [
      { key: 'record.copy_link', label: 'Copy link', run, confirmLabel: 'Copied' },
    ];
    render(<DetailActions actions={actions} />);

    openMenu(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy link' }));

    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    expect(screen.queryByRole('menuitem', { name: 'Copied' })).not.toBeInTheDocument();
  });

  it('an action with no confirmLabel still closes on select, exactly as before', async () => {
    const run = vi.fn();
    render(
      <DetailActions
        actions={[{ key: 'record.plain', label: 'Plain action', run }]}
      />,
    );

    openMenu(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Plain action' }));

    expect(run).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });
});

describe('the countdown takes the primary button\'s place (S6-06)', () => {
  it('swaps the primary for the countdown while an action is parked, and restores it on cancel', () => {
    const primary = <button type="button">Edit product</button>;
    const countdown = <div data-testid="countdown-slot">Deleting in 8s</div>;

    const { rerender } = render(<DetailActions actions={actionSet()} primary={primary} />);
    expect(screen.getByRole('button', { name: 'Edit product' })).toBeInTheDocument();

    // A record on its way out has one thing to offer, and it is Cancel.
    rerender(
      <DetailActions actions={actionSet()} primary={primary} pendingAction={countdown} />,
    );
    expect(screen.getByTestId('countdown-slot')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit product' })).toBeNull();

    // Nothing was applied, so the record is exactly what it was.
    rerender(
      <DetailActions actions={actionSet()} primary={primary} pendingAction={null} />,
    );
    expect(screen.getByRole('button', { name: 'Edit product' })).toBeInTheDocument();
    expect(screen.queryByTestId('countdown-slot')).toBeNull();
  });

  it('keeps the gear reachable while the countdown is running', () => {
    render(
      <DetailActions
        actions={actionSet()}
        primary={<button type="button">Edit product</button>}
        pendingAction={<div data-testid="countdown-slot" />}
      />,
    );

    expect(screen.getByRole('button', { name: 'Actions' })).toBeInTheDocument();
  });
});
