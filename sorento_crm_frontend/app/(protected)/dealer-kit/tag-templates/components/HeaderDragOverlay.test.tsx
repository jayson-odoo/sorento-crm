/**
 * PRICETAG-HEADER-DRAG: the header handle on a selected accessories box. Dragging it reports the
 * snapped, in-box spot in box millimetres; the press never reaches the box or the stage (so the box
 * does not move); and the inspector hides "on the border" for a moved header and offers Reset.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

type KonvaEvt = {
  cancelBubble: boolean;
  evt: { button: number };
  target: { x: () => number; y: () => number; position: (p: { x: number; y: number }) => void; getStage: () => null };
};

const pressed: KonvaEvt[] = [];
let dragTo = { x: 0, y: 0 };
let nextButton = 0;

vi.mock('react-konva', () => {
  const evt = (): KonvaEvt => {
    const e: KonvaEvt = {
      cancelBubble: false,
      evt: { button: nextButton },
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
          onDragStart={call('onDragStart')}
          data-text={String(props.text ?? '')}
        >
          {props.children}
        </div>
      );
    };
  return { Group: stand('group'), Rect: stand('rect'), Line: stand('line'), Text: stand('text') };
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
const text = { x_mm: 20, y_mm: 0, width_mm: 10, height_mm: 4 };
const frame = { x_mm: 0, y_mm: 2, width_mm: 50, height_mm: 38 };

function handle(onMove = vi.fn(), onDragState = vi.fn()) {
  const { container } = render(
    <HeaderDragOverlay
      layer={layer}
      text={text}
      fontSize_pt={9}
      onDragState={onDragState}
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

  it('while dragging, the text rides in the handle and the editor is told (it hides the box header)', () => {
    const onDragState = vi.fn();
    const el = handle(vi.fn(), onDragState);
    expect(el.querySelector('[data-kind="text"]')).toBeNull();
    fireEvent.dragStart(el);
    expect(onDragState).toHaveBeenLastCalledWith(true);
    expect(el.querySelector('[data-kind="text"]')?.getAttribute('data-text')).toBe('FREE');
    dragTo = { x: 0, y: 0 };
    fireEvent.dragEnd(el);
    expect(onDragState).toHaveBeenLastCalledWith(false);
    expect(el.querySelector('[data-kind="text"]')).toBeNull();
  });

  it('a middle-button press is not taken (it still pans the canvas)', () => {
    const el = handle();
    pressed.length = 0;
    nextButton = 1;
    fireEvent.mouseDown(el);
    nextButton = 0;
    expect(pressed[0].cancelBubble).toBe(false);
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
    expect(screen.queryByRole('button', { name: 'Reset header' })).toBeNull();
  });

  it('a moved header hides "on the border" and Reset clears the stored spot', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel layer={box({ headerPos: { x_mm: 2, y_mm: 3 } })} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />,
    );
    expect(screen.queryByLabelText('Header on the border')).toBeNull();
    expect(screen.queryByText('Behind the header')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Reset header' }));
    const sent = onUpdateProps.mock.calls.at(-1)![1] as Record<string, unknown>;
    // The key goes (undefined, dropped on save): a reset box saves like one never moved.
    expect('headerPos' in sent && sent.headerPos === undefined).toBe(true);
  });
});
