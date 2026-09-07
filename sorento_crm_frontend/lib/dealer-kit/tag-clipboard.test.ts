/**
 * The module-level clipboard store itself (S3, PLAN D3, AC-S3-5).
 *
 * `TagCanvasEditor.clipboard.test.tsx` pins the WIRING (a remounted editor
 * still pastes what a previous mount copied); this file pins the store in
 * isolation - set/get round-trip, subscribers notified, and that nothing
 * about it ever touches the network or any shared browser storage.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getTagClipboard,
  setTagClipboard,
  subscribeTagClipboard,
  type TagClipboardValue,
} from './tag-clipboard';
import type { TagLayer } from './tag-template-types';
import { defaultShapeProps } from './tag-template-types';

function layer(id: string): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: 5,
    y_mm: 5,
    width_mm: 10,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
  };
}

afterEach(() => {
  setTagClipboard(null);
});

describe('tag-clipboard (S3)', () => {
  it('starts empty', () => {
    expect(getTagClipboard()).toBeNull();
  });

  it('round-trips whatever is set', () => {
    const value: TagClipboardValue = {
      layers: [layer('l1')],
      roots: ['l1'],
      sourceDocId: 'tag-1',
    };

    setTagClipboard(value);

    expect(getTagClipboard()).toEqual(value);
  });

  it('overwrites the previous value - one clipboard, not a stack', () => {
    setTagClipboard({ layers: [layer('l1')], roots: ['l1'], sourceDocId: 'tag-1' });
    setTagClipboard({ layers: [layer('l2')], roots: ['l2'], sourceDocId: 'tag-2' });

    expect(getTagClipboard()?.roots).toEqual(['l2']);
  });

  it('clears with null', () => {
    setTagClipboard({ layers: [layer('l1')], roots: ['l1'], sourceDocId: 'tag-1' });
    setTagClipboard(null);

    expect(getTagClipboard()).toBeNull();
  });

  it('notifies every subscriber on a set, and stops once unsubscribed', () => {
    const heard: (TagClipboardValue | null)[] = [];
    const unsubscribe = subscribeTagClipboard(() => heard.push(getTagClipboard()));

    setTagClipboard({ layers: [layer('l1')], roots: ['l1'], sourceDocId: 'tag-1' });
    expect(heard).toHaveLength(1);
    expect(heard[0]?.roots).toEqual(['l1']);

    unsubscribe();
    setTagClipboard({ layers: [layer('l2')], roots: ['l2'], sourceDocId: 'tag-2' });
    expect(heard).toHaveLength(1);
  });

  it('supports more than one live subscriber independently', () => {
    const a = vi.fn();
    const b = vi.fn();
    const unsubA = subscribeTagClipboard(a);
    const unsubB = subscribeTagClipboard(b);

    setTagClipboard({ layers: [layer('l1')], roots: ['l1'], sourceDocId: 'tag-1' });

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);

    unsubA();
    setTagClipboard({ layers: [layer('l2')], roots: ['l2'], sourceDocId: 'tag-2' });

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(2);
    unsubB();
  });

  it('never touches localStorage, sessionStorage, cookies or the network (AC-S3-5)', () => {
    const localSetSpy = vi.spyOn(Storage.prototype, 'setItem');
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    setTagClipboard({ layers: [layer('l1')], roots: ['l1'], sourceDocId: 'tag-1' });
    getTagClipboard();
    setTagClipboard(null);

    expect(localSetSpy).not.toHaveBeenCalled();
    expect(document.cookie).toBe('');
    expect(fetchSpy).not.toHaveBeenCalled();

    localSetSpy.mockRestore();
    fetchSpy.mockRestore();
  });
});
