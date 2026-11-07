/**
 * PRICETAG-DESIGNER-GAPS item 1: the image inspector offers Flip horizontal and
 * Flip vertical as toggles that write `flipX` / `flipY` on the layer.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import type { ImageLayerProps, TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

function imageLayer(props: Partial<ImageLayerProps> = {}): TagLayer {
  return {
    id: 'img1',
    type: 'image',
    x_mm: 0,
    y_mm: 0,
    width_mm: 30,
    height_mm: 30,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'image', source: null, fit: 'contain', maskShape: 'none', ...props },
  } as TagLayer;
}

describe('Inspector image flip', () => {
  it('turns flip horizontal on', () => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={imageLayer()} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    const button = screen.getByRole('button', { name: /flip horizontal/i });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(button);
    expect(onUpdateProps).toHaveBeenCalledWith('img1', expect.objectContaining({ flipX: true }));
  });

  it('turns flip horizontal off again on a flipped layer', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel
        layer={imageLayer({ flipX: true })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );
    const button = screen.getByRole('button', { name: /flip horizontal/i });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(button);
    expect(onUpdateProps).toHaveBeenCalledWith('img1', expect.objectContaining({ flipX: false }));
  });

  it('turns flip vertical on without touching flip horizontal', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel
        layer={imageLayer({ flipX: true })}
        onUpdate={vi.fn()}
        onUpdateProps={onUpdateProps}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /flip vertical/i }));
    expect(onUpdateProps).toHaveBeenCalledWith(
      'img1',
      expect.objectContaining({ flipX: true, flipY: true }),
    );
  });
});
