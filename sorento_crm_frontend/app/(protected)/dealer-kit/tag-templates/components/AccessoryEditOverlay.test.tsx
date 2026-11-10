/**
 * Card edit mode: clicking empty space inside the card (not on an element) clears the element selection,
 * so a following Delete removes nothing.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('react-konva', () => {
  const stand = (kind: string) =>
    function Stand({
      children,
      name,
      onClick,
    }: {
      children?: React.ReactNode;
      name?: string;
      onClick?: (event: { cancelBubble: boolean }) => void;
    }) {
      return (
        <div data-kind={kind} data-name={name} onClick={() => onClick?.({ cancelBubble: false })}>
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
    card: {
      width_mm: 40,
      height_mm: 30,
      elements: [{ id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 2, y_mm: 2, width_mm: 10, height_mm: 4 }],
    },
  },
} as unknown as TagLayer;

describe('AccessoryEditOverlay', () => {
  it('a click on empty card space clears the selected element', () => {
    const onSelectElement = vi.fn();
    const { container } = render(
      <AccessoryEditOverlay
        layer={layer}
        target="card"
        elementId="dots"
        count={2}
        scale={4}
        onSelectElement={onSelectElement}
        onUpdateElement={vi.fn()}
      />,
    );
    const frame = container.querySelector('[data-name="accessory-card-frame"]') as HTMLElement;
    expect(frame).not.toBeNull();
    fireEvent.click(frame);
    expect(onSelectElement).toHaveBeenCalledWith(null);
  });

  it('a click on an element still selects it', () => {
    const onSelectElement = vi.fn();
    const { container } = render(
      <AccessoryEditOverlay
        layer={layer}
        target="card"
        elementId={null}
        count={2}
        scale={4}
        onSelectElement={onSelectElement}
        onUpdateElement={vi.fn()}
      />,
    );
    const rects = Array.from(container.querySelectorAll('[data-kind="rect"]')) as HTMLElement[];
    const element = rects.find((r) => r.dataset.name === 'accessory-card-element-dots')!;
    fireEvent.click(element);
    expect(onSelectElement).toHaveBeenCalledWith('dots');
  });
});
