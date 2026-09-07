/**
 * The toolbar row at 375px (r4c).
 *
 * The row is 561px of buttons at a 375px viewport - wider than the phone's
 * own window - and without its own scroll region the overflow bubbled up to
 * `window`, so the WHOLE editor scrolled sideways to see one more icon.
 * jsdom has no real layout engine, so this only pins the structural fix
 * (the row scrolls itself, its buttons never shrink to fit); the visual
 * check is a real browser at 375px.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Maximize2, Save } from 'lucide-react';

import { CanvasToolbar, type ToolbarTrailingAction } from './CanvasToolbar';

function noop() {}

function renderToolbar(trailing?: ToolbarTrailingAction[]) {
  return render(
    <CanvasToolbar
      tool="select"
      onToolChange={vi.fn()}
      onAddText={noop}
      onAddShape={noop}
      onAddImage={noop}
      onAddProductSlot={noop}
      onAddPriceBadge={noop}
      onAddBadge={noop}
      onAddBarcode={noop}
      onAddProduct={noop}
      onAddSet={noop}
      onAddAlternativesRow={noop}
      onAddAccessoriesStrip={noop}
      onUndo={noop}
      onRedo={noop}
      canUndo={false}
      canRedo={false}
      zoom={1}
      onZoomIn={noop}
      onZoomOut={noop}
      onZoomReset={noop}
      onFit={noop}
      onDeleteSelected={noop}
      onDuplicateSelected={noop}
      onGroupSelected={noop}
      onUngroupSelected={noop}
      hasSelection={false}
      hasMultiSelection={false}
      selectionIsGroup={false}
      trailing={trailing}
    />,
  );
}

describe('CanvasToolbar overflow at narrow viewports (r4c)', () => {
  it('scrolls the row itself instead of letting the window scroll', () => {
    const { container } = renderToolbar();
    const row = container.firstElementChild as HTMLElement;

    expect(row.className).toContain('overflow-x-auto');
    expect(row.className).toContain('flex-nowrap');
    expect(row.className).toContain('min-w-0');
  });

  /**
   * r4d: `overflow-x-auto` alone did not stop the PAGE scrolling.
   *
   * Every toolbar button carries its label in a `sr-only` span, and `sr-only`
   * is `position: absolute`. An absolutely positioned box is clipped by an
   * ancestor's overflow only when that ancestor is in its containing-block
   * chain, and a `position: static` row is not - so the labels laid out
   * against the initial containing block and stretched the document instead.
   * Measured at 375px on the request designer: `documentElement.scrollWidth`
   * was 898, exactly the right edge of the last label, and setting the row to
   * `position: relative` took it to 375 with nothing else changed.
   */
  it('contains its own absolutely positioned labels so the page cannot scroll', () => {
    const { container } = renderToolbar();
    const row = container.firstElementChild as HTMLElement;

    expect(row.className).toContain('relative');
  });

  it('never shrinks a button to make the row fit', () => {
    renderToolbar();

    const select = screen.getByRole('button', { name: 'Select' });
    expect(select.className).toContain('shrink-0');
  });
});

// ---------------------------------------------------------------------------
// Trailing group overflow below md (S7, grill G3, AC-S7-3).
//
// jsdom has no real layout engine (see the file's own header comment), so
// this pins the STRUCTURAL contract only: an inline rendering of `trailing`
// visible at md and up, an overflow "..." trigger visible only below md that
// opens the SAME actions in a menu. The actual breakpoint switch (which one
// is VISUALLY showing at 375px vs 1280px) is a real-browser check.
// ---------------------------------------------------------------------------

function trailingActions(onSave: () => void = () => {}): ToolbarTrailingAction[] {
  return [
    { id: 'save', icon: Save, label: 'Save', onClick: onSave },
    { id: 'full-screen', icon: Maximize2, label: 'Full screen', onClick: () => {} },
  ];
}

function openOverflowMenu() {
  fireEvent.pointerDown(
    screen.getByTestId('toolbar-trailing-overflow-trigger'),
    new MouseEvent('pointerdown', { bubbles: true, button: 0 }),
  );
}

describe('trailing group collapses into an overflow menu below md (S7, AC-S7-3)', () => {
  it('renders an inline trailing group hidden below md, visible at md and up', () => {
    const { container } = renderToolbar(trailingActions());

    const inline = container.querySelector('[data-testid="toolbar-trailing-inline"]');
    expect(inline).not.toBeNull();
    expect(inline!.className).toContain('hidden');
    expect(inline!.className).toContain('md:flex');
    expect(within(inline as HTMLElement).getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it('renders a single overflow trigger visible only below md, hidden at md and up', () => {
    const { container } = renderToolbar(trailingActions());

    const trigger = screen.getByTestId('toolbar-trailing-overflow-trigger');
    expect(trigger.className).toContain('md:hidden');
    // Exactly one overflow button for the whole trailing group, not one per
    // action - the point of collapsing them.
    expect(
      container.querySelectorAll('[data-testid="toolbar-trailing-overflow-trigger"]'),
    ).toHaveLength(1);
  });

  it('opens the SAME actions in a menu, reachable and functional', () => {
    renderToolbar(trailingActions());

    // Radix opens its DropdownMenu on pointerdown, not click (S1) - a plain
    // `fireEvent.click` never reaches it, and the trigger carries no explicit
    // `onClick` of its own to fake that: adding one double-toggles a real
    // mouse click (pointerdown opens it, the click that follows would close
    // it right back).
    openOverflowMenu();

    const menu = screen.getByRole('menu');
    expect(within(menu).getByText('Save')).toBeInTheDocument();
    expect(within(menu).getByText('Full screen')).toBeInTheDocument();
  });

  it('renders each action as a real DropdownMenuItem - arrow-key navigable, closes itself once picked (S2)', async () => {
    const onSave = vi.fn();
    renderToolbar(trailingActions(onSave));

    openOverflowMenu();
    const menu = screen.getByRole('menu');
    // A raw <button> dropped into DropdownMenuContent is invisible to
    // Radix's own item list (no role, no arrow-key nav) - the S2 fix renders
    // real DropdownMenuItems instead.
    expect(within(menu).getByRole('menuitem', { name: 'Save' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Full screen' })).toBeInTheDocument();

    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledTimes(1);
    // Picking a real DropdownMenuItem closes the whole menu tree on its own
    // (Radix's own default) - the r6 review bug was a raw button staying
    // open after Save because it was never part of that item list. Radix's
    // own close animation unmounts it a tick after the click, not
    // synchronously with it.
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('renders neither the inline group nor the overflow trigger when trailing is absent', () => {
    const { container } = renderToolbar(undefined);

    expect(container.querySelector('[data-testid="toolbar-trailing-inline"]')).toBeNull();
    expect(screen.queryByTestId('toolbar-trailing-overflow-trigger')).not.toBeInTheDocument();
  });
});
