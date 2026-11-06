/**
 * PRICETAG-ACCESSORIES: the "Accessories" box inspector. Header text and the "+" badge are per box
 * (owner, 6 Nov: "FREE" vs "ACCESSORIES INCLUDED"), the direction is per box (Q3), and a list that
 * does not fit is never silent (A6, the feature icons pattern).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

function box(over: Partial<TagLayer> = {}): TagLayer {
  return {
    id: 'acc1',
    type: 'accessories',
    x_mm: 0,
    y_mm: 0,
    width_mm: 45,
    height_mm: 40,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultAccessoriesProps(),
    ...over,
  } as TagLayer;
}

describe('Inspector, accessories box', () => {
  it('edits the header text of THIS box', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    fireEvent.change(screen.getByLabelText('Header text'), { target: { value: 'FREE' } });
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ headerText: 'FREE' }));
  });

  it('switches the box horizontal, and only then offers a card width', () => {
    const onUpdateProps = vi.fn();
    const { rerender } = render(
      <InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />,
    );
    expect(screen.queryByLabelText('Card width (mm)')).toBeNull();
    fireEvent.click(screen.getByRole('radio', { name: 'Horizontal' }));
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ direction: 'horizontal' }));
    rerender(
      <InspectorPanel
        layer={box({ props: { ...defaultAccessoriesProps(), direction: 'horizontal' } })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );
    expect(screen.getByLabelText('Card width (mm)')).toBeInTheDocument();
  });

  it('turns the plus badge off', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show the plus badge' }));
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ showBadge: false }));
  });

  it('warns how many of the previewed accessories do not fit', () => {
    render(
      <InspectorPanel
        layer={box({ height_mm: 30 })}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        accessoryFit={{ count: 5, lines: 2 }}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      /^\d of 5 accessories do not fit this box\. Make the box bigger or the cards smaller\.$/,
    );
  });

  it('says nothing when they all fit, or nothing is previewed', () => {
    const { rerender } = render(
      <InspectorPanel layer={box({ height_mm: 200 })} onUpdate={vi.fn()} onUpdateProps={vi.fn()} accessoryFit={{ count: 3, lines: 2 }} />,
    );
    expect(screen.queryByText(/do not fit this box/)).toBeNull();
    rerender(<InspectorPanel layer={box({ height_mm: 10 })} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
    expect(screen.queryByText(/do not fit this box/)).toBeNull();
  });
});
