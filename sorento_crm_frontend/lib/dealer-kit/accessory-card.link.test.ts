import { describe, expect, it } from 'vitest';
import {
  accessoryDesign,
  changedLinkedDesign,
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
