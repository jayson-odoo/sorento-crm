/**
 * TAG-ACC-CARD-RESIZE Q3: in Edit card mode the card frame has resize handles. A resize sets the
 * card's design size (every card in the box) in card millimetres, the box's shrink undone; the
 * elements keep their own millimetres. The footer frame has none.
 */
import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

type FakeNode = { width: () => number; height: () => number; scaleX: (v?: number) => number; scaleY: (v?: number) => number };

vi.mock('react-konva', () => {
  const stand = (kind: string) =>
    function Stand({
      children,
      name,
      onTransformEnd,
    }: {
      children?: React.ReactNode;
      name?: string;
      onTransformEnd?: (event: { target: FakeNode; cancelBubble: boolean }) => void;
    }) {
      return (
        <div
          data-kind={kind}
          data-name={name}
          onDoubleClick={() => {
            // The frame drawn 160 x 120 px, stretched to 1.5 x 0.5 by its handles.
            const node: FakeNode = { width: () => 160, height: () => 120, scaleX: () => 1.5, scaleY: () => 0.5 };
            onTransformEnd?.({ target: node, cancelBubble: false });
          }}
        >
          {children}
        </div>
      );
    };
  return { Group: stand('group'), Rect: stand('rect'), Line: stand('line'), Transformer: stand('transformer') };
});

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { AccessoryEditOverlay } from './AccessoryEditOverlay';

const layer = {
  id: 'acc1', type: 'accessories', x_mm: 0, y_mm: 0, width_mm: 60, height_mm: 80, rotation_deg: 0,
  z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
  props: {
    ...defaultAccessoriesProps(),
    showHeader: false,
    showBadge: false,
    gap_mm: 0,
    card: {
      width_mm: 40,
      height_mm: 30,
      elements: [{ id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 2, y_mm: 2, width_mm: 10, height_mm: 4 }],
    },
  },
} as unknown as TagLayer;

const renderOverlay = (over: Partial<Parameters<typeof AccessoryEditOverlay>[0]> = {}) => {
  const onResizeCard = vi.fn();
  const out = render(
    <AccessoryEditOverlay
      layer={layer}
      target="card"
      elementId={null}
      count={2}
      scale={4}
      onSelectElement={vi.fn()}
      onUpdateElement={vi.fn()}
      onResizeCard={onResizeCard}
      {...over}
    />,
  );
  return { ...out, onResizeCard };
};

describe('AccessoryEditOverlay card frame resize', () => {
  it('draws a frame transformer while no element is selected', () => {
    const { container } = renderOverlay();
    expect(container.querySelector('[data-name="accessory-card-frame-transformer"]')).not.toBeNull();
  });

  it('a frame resize sets the card design size in card millimetres', () => {
    const { container, onResizeCard } = renderOverlay();
    // 2 cards of 40 x 30 at 100% fit 60 x 80 (1.5 + 60 + 1.5 = 63 high > 80? no: 60 + 3 = 63 <= 80), scale 4 px/mm.
    fireEvent.doubleClick(container.querySelector('[data-name="accessory-card-frame"]') as HTMLElement);
    // 160 * 1.5 / 4 = 60 mm; 120 * 0.5 / 4 = 15 mm.
    expect(onResizeCard).toHaveBeenCalledWith({ width_mm: 60, height_mm: 15 });
  });

  it('no frame transformer while an element is selected, nor on the footer', () => {
    const selected = renderOverlay({ elementId: 'dots' });
    expect(selected.container.querySelector('[data-name="accessory-card-frame-transformer"]')).toBeNull();
    selected.unmount();
    const footer = renderOverlay({ target: 'footer' });
    expect(footer.container.querySelector('[data-name="accessory-card-frame-transformer"]')).toBeNull();
  });
});
