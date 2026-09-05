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
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CanvasToolbar } from './CanvasToolbar';

function noop() {}

function renderToolbar() {
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
