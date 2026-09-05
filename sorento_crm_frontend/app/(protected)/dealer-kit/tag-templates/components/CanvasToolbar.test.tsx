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

  it('never shrinks a button to make the row fit', () => {
    renderToolbar();

    const select = screen.getByRole('button', { name: 'Select' });
    expect(select.className).toContain('shrink-0');
  });
});
