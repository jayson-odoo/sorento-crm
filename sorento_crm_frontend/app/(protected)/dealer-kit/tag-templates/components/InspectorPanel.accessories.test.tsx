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

  it('the "+" badge is off on a new box and turns on with its own switch', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    const badge = screen.getByRole('checkbox', { name: 'Show the plus badge' });
    expect(badge).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(badge);
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ showBadge: true }));
  });

  it('item layout: picture above text (default) or left of text', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    expect(screen.getByRole('radio', { name: 'Picture above text' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('radio', { name: 'Picture left of text' }));
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ itemLayout: 'side' }));
  });

  it('header: hide it, or set it on the border', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    expect(screen.getByRole('checkbox', { name: 'Header on the border' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Header on the border' }));
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ headerOnBorder: false }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show header' }));
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ showHeader: false }));
  });

  it('a hidden header hides its text box and style', () => {
    render(
      <InspectorPanel
        layer={box({ props: { ...defaultAccessoriesProps(), showHeader: false } })}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText('Header text')).toBeNull();
    expect(screen.queryByText('Header text style')).toBeNull();
  });

  it('the frame can be switched off', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show frame' }));
    expect(onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ showFrame: false }));
  });

  it('name and spec text use the text layer typography controls (italic on the spec)', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={box()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    expect(screen.getByText('Name text')).toBeInTheDocument();
    expect(screen.getByText('Spec text')).toBeInTheDocument();
    // Header, name, spec: one Italic toggle each, in that order.
    const italics = screen.getAllByRole('button', { name: 'Italic' });
    expect(italics).toHaveLength(3);
    fireEvent.click(italics[2]);
    expect(onUpdateProps).toHaveBeenCalledWith(
      'acc1',
      expect.objectContaining({ specStyle: expect.objectContaining({ italic: true }) }),
    );
    expect(screen.queryByLabelText('Line Height')).toBeNull();
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
