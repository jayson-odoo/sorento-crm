import { describe, expect, it } from 'vitest';
import {
  accessoryDesign,
  applyLinkActions,
  changedLinkedDesign,
  linkRefreshActions,
  linkCorrectionPatches,
  designKey,
  detachLinked,
  linkedPresetIds,
  setLinkedDesign,
} from './accessory-card';
import { defaultAccessoriesProps, type AccessoriesLayerProps } from './tag-template-types';

const box = (id: string, over: Partial<AccessoriesLayerProps> = {}) => ({
  id,
  props: { ...defaultAccessoriesProps(), presetId: 'p1', ...over } as AccessoriesLayerProps,
});
const key = (layer: { props: AccessoriesLayerProps }) => designKey(accessoryDesign(layer.props));

describe('live link helpers', () => {
  const a = box('a');
  const b = box('b');

  it('lists the linked preset ids once', () => {
    expect(linkedPresetIds([a, b, { id: 'c', props: { kind: 'text' } }, box('d', { presetId: null })])).toEqual(['p1']);
  });

  it('finds no change when every box matches the baseline', () => {
    expect(changedLinkedDesign([a, b], 'p1', key(a))).toBeNull();
  });

  it('finds the box the user changed, even when it is not the first', () => {
    const edited = box('b', { headerText: 'NEW' });
    expect(changedLinkedDesign([a, edited], 'p1', key(a))?.headerText).toBe('NEW');
  });

  it('when both changed, the last one wins', () => {
    const one = box('a', { headerText: 'ONE' });
    const two = box('b', { headerText: 'TWO' });
    expect(changedLinkedDesign([one, two], 'p1', key(a))?.headerText).toBe('TWO');
  });

  it('applies a design to every linked box and keeps the subject keys', () => {
    const own = box('a', { subjectPart: 2 });
    const design = accessoryDesign(box('x', { headerText: 'SHARED' }).props);
    const [out] = setLinkedDesign([own], 'p1', design);
    expect(out.props.headerText).toBe('SHARED');
    expect(out.props.subjectPart).toBe(2);
    expect(out.props.presetId).toBe('p1');
  });

  it('detaches and keeps the design', () => {
    const [out] = detachLinked([box('a', { headerText: 'KEEP' })], 'p1');
    expect(out.props.presetId).toBeNull();
    expect(out.props.headerText).toBe('KEEP');
  });
});

describe('no baseline and correction patches', () => {
  it('a box with no baseline is never "changed": it follows the server instead of being pushed', () => {
    const odd = box('a', { headerText: 'DIFFERENT' });
    expect(changedLinkedDesign([odd], 'p1', undefined)).toBeNull();
  });

  it('builds a patch per linked box that remembers the design it was worked out from', () => {
    const own = box('a', { headerText: 'OLD', subjectPart: 3 });
    const server = accessoryDesign(box('x', { headerText: 'SERVER' }).props);
    const [patch] = linkCorrectionPatches([own], [{ kind: 'set', id: 'p1', design: server }]);
    expect(patch.layerId).toBe('a');
    expect(patch.expectedKey).toBe(key(own));
    expect(patch.props.headerText).toBe('SERVER');
    expect(patch.props.subjectPart).toBe(3);
    const [gone] = linkCorrectionPatches([own], [{ kind: 'detach', id: 'p1' }]);
    expect(gone.props.presetId).toBeNull();
    expect(gone.props.headerText).toBe('OLD');
  });
});

describe('a copy of linked boxes follows the saved template', () => {
  const stale = box('a', { headerText: 'OLD' });
  const server = accessoryDesign(box('x', { headerText: 'SERVER' }).props);

  it('takes the template design where the box differs, and nothing where it already matches', async () => {
    const actions = await linkRefreshActions([stale], async () => ({ design: server }));
    expect(actions).toEqual([{ kind: 'set', id: 'p1', design: server }]);
    const [out] = applyLinkActions([stale], actions);
    expect(out.props.headerText).toBe('SERVER');
    expect(await linkRefreshActions([out], async () => ({ design: server }))).toEqual([]);
  });

  it('detaches where the template is gone, keeping the design', async () => {
    const actions = await linkRefreshActions([stale], async () => null);
    expect(actions).toEqual([{ kind: 'detach', id: 'p1' }]);
    const [out] = applyLinkActions([stale], actions);
    expect(out.props.presetId).toBeNull();
    expect(out.props.headerText).toBe('OLD');
  });

  it('leaves a box alone when its template cannot be read', async () => {
    expect(await linkRefreshActions([stale], async () => Promise.reject(new Error('down')))).toEqual([]);
  });
});
