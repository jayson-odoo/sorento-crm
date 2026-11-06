/**
 * DESIGNER-RICH-TEXT owner bug (6 Nov): the selection rule for a right-click and the platform's
 * own modifier keys.
 *
 *  - Right-click on any layer under the pointer that is already selected keeps the selection
 *    (the menu acts on it); on an unselected layer it selects just that one; on empty canvas it
 *    keeps the selection.
 *  - Cmd+click (macOS) / Ctrl+click (elsewhere) adds to the selection like Shift+click.
 *  - On macOS Ctrl+click is the system right-click, so it never changes the selection itself.
 *  - The context menu writes shortcuts with the command symbol on macOS.
 *
 * Written test-FIRST: `canvas-input.ts` does not exist yet.
 */
import { describe, expect, it } from 'vitest';

import type { TagLayer } from './tag-template-types';
import { defaultShapeProps } from './tag-template-types';
import {
  isAdditiveClick,
  isMacContextClick,
  layersAt,
  selectionForContextMenu,
  shortcutLabel,
} from './canvas-input';

function box(id: string, z: number, x = 0, y = 0, w = 80, h = 60): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: x,
    y_mm: y,
    width_mm: w,
    height_mm: h,
    rotation_deg: 0,
    z_index: z,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
  };
}

describe('selectionForContextMenu', () => {
  const selected = new Set(['a', 'b']);

  it('keeps the selection when ANY layer under the pointer is selected (frame on top)', () => {
    expect(selectionForContextMenu(selected, ['frame', 'a'])).toBeNull();
  });

  it('keeps the selection when the top layer is selected', () => {
    expect(selectionForContextMenu(selected, ['b'])).toBeNull();
  });

  it('selects just the top layer when nothing under the pointer is selected', () => {
    expect(selectionForContextMenu(selected, ['c', 'frame'])).toEqual(new Set(['c']));
  });

  it('the layer Konva drew under the pointer decides when it reports one (review S3)', () => {
    // A selected background card under an unselected text: right-click on the text selects it.
    expect(selectionForContextMenu(new Set(['card']), ['text', 'card'], 'text')).toEqual(new Set(['text']));
    // A selected text under a frame (Konva hits the text through the frame's transparent inside).
    expect(selectionForContextMenu(selected, ['frame', 'a'], 'a')).toBeNull();
  });

  it('keeps the selection on empty canvas', () => {
    expect(selectionForContextMenu(selected, [])).toBeNull();
  });
});

describe('layersAt', () => {
  it('lists every selectable layer under the point, top first', () => {
    const layers = [box('frame', 3), box('a', 1, 5, 5, 20, 10), box('b', 2, 40, 5, 20, 10)];
    expect(layersAt(layers, 10, 10, new Set())).toEqual(['frame', 'a']);
  });

  it('skips hidden and locked layers', () => {
    const layers = [{ ...box('hidden', 3), visible: false }, { ...box('locked', 2), locked: true }, box('a', 1)];
    expect(layersAt(layers, 10, 10, new Set())).toEqual(['a']);
  });
});

describe('modifier keys', () => {
  const ev = (over: Partial<MouseEvent>) => ({ shiftKey: false, metaKey: false, ctrlKey: false, button: 0, ...over });

  it('Shift adds everywhere', () => {
    expect(isAdditiveClick(ev({ shiftKey: true }), true)).toBe(true);
    expect(isAdditiveClick(ev({ shiftKey: true }), false)).toBe(true);
  });

  it('Cmd adds on macOS, Ctrl elsewhere', () => {
    expect(isAdditiveClick(ev({ metaKey: true }), true)).toBe(true);
    expect(isAdditiveClick(ev({ ctrlKey: true }), true)).toBe(false);
    expect(isAdditiveClick(ev({ ctrlKey: true }), false)).toBe(true);
  });

  it('a plain click does not add', () => {
    expect(isAdditiveClick(ev({}), true)).toBe(false);
  });

  it('Ctrl+click is a context click on macOS only', () => {
    expect(isMacContextClick(ev({ ctrlKey: true }), true)).toBe(true);
    expect(isMacContextClick(ev({ ctrlKey: true }), false)).toBe(false);
    expect(isMacContextClick(ev({}), true)).toBe(false);
  });
});

describe('shortcutLabel', () => {
  it('uses the command symbol on macOS and Ctrl+ elsewhere', () => {
    expect(shortcutLabel('G', true)).toBe('⌘G');
    expect(shortcutLabel('G', false)).toBe('Ctrl+G');
  });

  it('writes Shift the platform way', () => {
    expect(shortcutLabel('Z', true, true)).toBe('⇧⌘Z');
    expect(shortcutLabel('Z', false, true)).toBe('Ctrl+Shift+Z');
  });
});
