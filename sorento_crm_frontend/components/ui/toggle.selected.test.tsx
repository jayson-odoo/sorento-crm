/**
 * TOGGLE-SELECTED - the selected option of every toggle is the primary colour.
 *
 * The selected state used `bg-accent` (zinc-100), a hair darker than the white of
 * the unselected options, so on Contact Tag settings "Not set | On | Off" the
 * chosen value could not be told apart. The Switch's on state is `bg-primary`
 * (switch.tsx); a selected toggle now uses the same token.
 *
 * Plan: documentation/plans/design-system/PLAN-toggle-selected-20oct.md
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Toggle } from './toggle';
import { ToggleGroup, ToggleGroupItem } from './toggle-group';

const SELECTED_BG = 'data-[state=on]:bg-primary';
const SELECTED_FG = 'data-[state=on]:text-primary-foreground';

function classOf(el: Element | null) {
  return el?.getAttribute('class') ?? '';
}

describe('a selected toggle is the primary colour', () => {
  it('a pressed Toggle carries the primary background and foreground', () => {
    render(<Toggle defaultPressed>Bold</Toggle>);
    const el = screen.getByRole('button', { name: 'Bold' });
    expect(el.getAttribute('data-state')).toBe('on');
    expect(classOf(el)).toContain(SELECTED_BG);
    expect(classOf(el)).toContain(SELECTED_FG);
    expect(classOf(el)).not.toContain('data-[state=on]:bg-accent');
  });

  for (const variant of ['default', 'outline'] as const) {
    it(`the selected ToggleGroupItem (${variant}) is primary and the others are not on`, () => {
      render(
        <ToggleGroup type="single" variant={variant} size="sm" defaultValue="on" aria-label="AI replies">
          <ToggleGroupItem value="unset">Not set</ToggleGroupItem>
          <ToggleGroupItem value="on">On</ToggleGroupItem>
          <ToggleGroupItem value="off">Off</ToggleGroupItem>
        </ToggleGroup>,
      );
      const on = screen.getByRole('radio', { name: 'On' });
      expect(on.getAttribute('data-state')).toBe('on');
      expect(on.getAttribute('aria-checked')).toBe('true');
      expect(classOf(on)).toContain(SELECTED_BG);
      expect(classOf(on)).toContain(SELECTED_FG);
      expect(classOf(on)).not.toContain('data-[state=on]:bg-accent');
      expect(screen.getByRole('radio', { name: 'Not set' }).getAttribute('data-state')).toBe('off');
    });
  }

  it('the selected item answers hover in its own colour, not the grey of an unselected one', () => {
    render(<Toggle defaultPressed>Bold</Toggle>);
    expect(classOf(screen.getByRole('button', { name: 'Bold' }))).toContain('data-[state=on]:hover:bg-primary/90');
  });

  it('a disabled selected item is still dimmed', () => {
    render(
      <Toggle defaultPressed disabled>
        Bold
      </Toggle>,
    );
    expect(classOf(screen.getByRole('button', { name: 'Bold' }))).toContain('disabled:opacity-50');
  });
});
