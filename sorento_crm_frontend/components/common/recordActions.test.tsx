/**
 * The `disabledReason` primitive (S1 of `PLAN-scm-loading-plan-feedback-2sep.md`, section 3.1).
 *
 * A disabled `RecordAction` can now say WHY - "Sent plans are cancelled, not deleted",
 * "Already cancelled" - and this is the one place that reason reaches the DOM, as the
 * item's `title` (hover) and `aria-description` (screen reader). Every existing consumer
 * left the field unset, so this only has to prove the new field renders, and that leaving
 * it unset renders exactly as before.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RowActionsMenu } from './RowActionsMenu';
import type { RecordAction } from './recordActions';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

/** Radix opens on pointerdown, which jsdom does not synthesize from a click. */
async function openMenu(ariaLabel: string) {
  const trigger = await screen.findByRole('button', { name: ariaLabel });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
  return screen.findByRole('menu');
}

describe('RecordActionItem - disabledReason', () => {
  it('forwards disabledReason as title and aria-description on a disabled item', async () => {
    const actions: RecordAction[] = [
      {
        key: 'widget.delete',
        label: 'Delete widget',
        kind: 'destructive',
        disabled: true,
        disabledReason: 'Sent plans are cancelled, not deleted',
        run: () => {},
      },
    ];
    render(<RowActionsMenu actions={actions} ariaLabel="widget" />);

    await openMenu('widget actions');
    const item = screen.getByRole('menuitem', { name: 'Delete widget' });
    expect(item.getAttribute('title')).toBe('Sent plans are cancelled, not deleted');
    expect(item.getAttribute('aria-description')).toBe('Sent plans are cancelled, not deleted');
  });

  it('leaves title and aria-description unset when disabledReason is not given', async () => {
    const actions: RecordAction[] = [
      { key: 'widget.edit', label: 'Edit widget', run: () => {} },
    ];
    render(<RowActionsMenu actions={actions} ariaLabel="widget" />);

    await openMenu('widget actions');
    const item = screen.getByRole('menuitem', { name: 'Edit widget' });
    expect(item.getAttribute('title')).toBeNull();
    expect(item.getAttribute('aria-description')).toBeNull();
  });
});
