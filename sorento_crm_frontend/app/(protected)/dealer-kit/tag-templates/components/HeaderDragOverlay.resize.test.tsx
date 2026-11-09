/**
 * PRICETAG-HEADER-DRAG round 2: a selected header gets the same Transformer handles as any canvas
 * element (no rotation); a resize reports the new band in box mm, and a click selects the header.
 */
import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const node = { x: 20, y: 8, sx: 1, sy: 1 };
vi.mock('react-konva', () => {
  const target = {
    x: () => node.x,
    y: () => node.y,
    scaleX: (v?: number) => (v === undefined ? node.sx : ((node.sx = v), undefined)),
    scaleY: (v?: number) => (v === undefined ? node.sy : ((node.sy = v), undefined)),
    position: () => {},
    getStage: () => null,
  };
  const stand = (kind: string) =>
    function Stand(props: Record<string, unknown> & { children?: React.ReactNode }) {
      const call = (name: string) => () =>
        (props[name] as ((e: unknown) => void) | undefined)?.({ cancelBubble: false, evt: { button: 0 }, target });
      return (
        <div
          data-kind={kind}
          data-name={props.name as string}
          data-rotate={String(props.rotateEnabled ?? '')}
          data-ratio={String(props.keepRatio ?? '')}
          onClick={call('onClick')}
          onMouseUp={call('onTransformEnd')}
        >
          {props.children}
        </div>
      );
    };
  return { Group: stand('group'), Rect: stand('rect'), Line: stand('line'), Text: stand('text'), Transformer: stand('transformer') };
});

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { HeaderDragOverlay } from './HeaderDragOverlay';

const SCALE = 4;
const layer = {
  id: 'acc1', type: 'accessories', x_mm: 0, y_mm: 0, width_mm: 50, height_mm: 40, rotation_deg: 0,
  z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
  props: { ...defaultAccessoriesProps(), headerText: 'FREE' },
} as unknown as TagLayer;

function mount(selected: boolean, onResize = vi.fn(), onSelect = vi.fn()) {
  const { container } = render(
    <HeaderDragOverlay
      layer={layer}
      text={{ x_mm: 5, y_mm: 2, width_mm: 10, height_mm: 4 }}
      header={{ x_mm: 0, y_mm: 0, width_mm: 10, height_mm: 4, fontSize_pt: 9, onBorder: false, moved: true, wrap: false, fill: null, radius_mm: 0, padding: { top: 0, right: 0, bottom: 0, left: 0 }, text: { x_mm: 0, y_mm: 0, width_mm: 10, height_mm: 4 } }}
      frame={null}
      boxWidth_mm={50}
      boxHeight_mm={40}
      scale={SCALE}
      selected={selected}
      onSelect={onSelect}
      onResize={onResize}
      onMove={vi.fn()}
    />,
  );
  return container;
}

describe('header resize handles', () => {
  it('no handles until the header is selected; then a Transformer with no rotation', () => {
    expect(mount(false).querySelector('[data-kind="transformer"]')).toBeNull();
    const t = mount(true).querySelector('[data-kind="transformer"]');
    expect(t).not.toBeNull();
    expect(t!.getAttribute('data-rotate')).toBe('false');
    // Width and height resize independently, like a text element (Konva's default keeps the ratio).
    expect(t!.getAttribute('data-ratio')).toBe('false');
  });

  it('a click on the header selects it', () => {
    const onSelect = vi.fn();
    const c = mount(false, vi.fn(), onSelect);
    fireEvent.click(c.querySelector('[data-name="accessory-header-handle"]')!);
    expect(onSelect).toHaveBeenCalled();
  });

  it('a resize reports the new band in box mm, scale reset', () => {
    const onResize = vi.fn();
    const c = mount(true, onResize);
    node.x = 6 * SCALE;
    node.y = 3 * SCALE;
    node.sx = 2;
    node.sy = 1.5;
    fireEvent.mouseUp(c.querySelector('[data-name="accessory-header-handle"]')!);
    expect(onResize).toHaveBeenCalledWith({ x_mm: 6, y_mm: 3, width_mm: 20, height_mm: 6 });
    expect(node.sx).toBe(1);
    expect(node.sy).toBe(1);
  });
});
