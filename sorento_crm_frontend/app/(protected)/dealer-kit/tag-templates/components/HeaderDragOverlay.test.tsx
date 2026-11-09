/**
 * PRICETAG-HEADER-DRAG: the header handle on a selected accessories box. Dragging it reports the
 * snapped, in-box spot in box millimetres; the press never reaches the box or the stage (so the box
 * does not move); and the inspector hides "on the border" for a moved header and offers Reset.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

type KonvaEvt = {
  cancelBubble: boolean;
  target: { x: () => number; y: () => number; position: (p: { x: number; y: number }) => void; getStage: () => null };
};

const pressed: KonvaEvt[] = [];
let dragTo = { x: 0, y: 0 };

vi.mock('react-konva', () => {
  const evt = (): KonvaEvt => {
    const e: KonvaEvt = {
      cancelBubble: false,
      target: {
        x: () => dragTo.x,
        y: () => dragTo.y,
        position: (p) => {
          dragTo = p;
        },
        getStage: () => null,
      },
    };
    pressed.push(e);
    return e;
  };
  const stand = (kind: string) =>
    function Stand(props: Record<string, unknown> & { children?: React.ReactNode }) {
      const call = (name: string) => () => (props[name] as ((e: KonvaEvt) => void) | undefined)?.(evt());
      return (
        <div
          data-kind={kind}
          data-name={props.name as string}
          data-x={String(props.x ?? '')}
          onMouseDown={call('onMouseDown')}
          onClick={call('onClick')}
          onDragEnd={call('onDragEnd')}
        >
          {props.children}
        </div>
      );
    };
  return { Group: stand('group'), Rect: stand('rect'), Line: stand('line') };
});
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { HeaderDragOverlay } from './HeaderDragOverlay';
import { InspectorPanel } from './InspectorPanel';

const SCALE = 4;
const layer = {
  id: 'acc1', type: 'accessories', x_mm: 10, y_mm: 10, width_mm: 50, height_mm: 40, rotation_deg: 0,
  z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
  props: { ...defaultAccessoriesProps(), headerText: 'FREE' },
} as unknown as TagLayer;
const header = { x_mm: 20, y_mm: 0, width_mm: 10, height_mm: 4 };
const frame = { x_mm: 0, y_mm: 2, width_mm: 50, height_mm: 38 };

function handle(onMove = vi.fn()) {
  const { container } = render(
    <HeaderDragOverlay
      layer={layer}
      header={header}
      frame={frame}
      boxWidth_mm={50}
      boxHeight_mm={40}
      scale={SCALE}
      onMove={onMove}
    />,
  );
  return container.querySelector('[data-name="accessory-header-handle"]') as HTMLElement;
}

describe('HeaderDragOverlay', () => {
  it('a drop reports the spot in box mm, snapped onto the bottom border', () => {
    const onMove = vi.fn();
    const el = handle(onMove);
    // Dropped with its bottom 0.6 mm above the frame's bottom edge (40 mm): it snaps onto it.
    dragTo = { x: 3 * SCALE, y: 35.4 * SCALE };
    fireEvent.dragEnd(el);
    expect(onMove).toHaveBeenCalledWith({ x_mm: 3, y_mm: 36 });
  });

  it('a drop past the box is kept inside it', () => {
    const onMove = vi.fn();
    const el = handle(onMove);
    dragTo = { x: 90 * SCALE, y: -20 * SCALE };
    fireEvent.dragEnd(el);
    expect(onMove).toHaveBeenCalledWith({ x_mm: 40, y_mm: 0 });
  });

  it('the press is the header\'s: it never bubbles to the box or the stage', () => {
    const el = handle();
    pressed.length = 0;
    fireEvent.mouseDown(el);
    fireEvent.click(el);
    expect(pressed).toHaveLength(2);
    expect(pressed.every((e) => e.cancelBubble)).toBe(true);
  });
});

describe('Inspector header controls (owner Q3)', () => {
  const box = (extra: Record<string, unknown>) =>
    ({ ...layer, props: { ...defaultAccessoriesProps(), headerOnBorder: true, ...extra } }) as unknown as TagLayer;

  it('an unmoved header keeps "Header on the border" and shows no Reset', () => {
    render(<InspectorPanel layer={box({})} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
    expect(screen.getByLabelText('Header on the border')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reset header position' })).toBeNull();
  });

  it('a moved header hides "on the border" and Reset clears the stored spot', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel layer={box({ headerPos: { x_mm: 2, y_mm: 3 } })} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />,
    );
    expect(screen.queryByLabelText('Header on the border')).toBeNull();
    expect(screen.queryByText('Behind the header')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Reset header position' }));
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ headerPos: null }));
  });
});
