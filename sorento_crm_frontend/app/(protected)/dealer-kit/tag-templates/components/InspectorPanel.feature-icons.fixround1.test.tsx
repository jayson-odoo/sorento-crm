/**
 * Feature icons review fix round 1: B2 the inspector opens the icon library ("Manage icons"),
 * N3 alignment is one single-choice group. Owner 21:0x: no per-layer icon order any more (the
 * spec's Icon order decides), so the inspector lists no icons and moves none.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const layer = {
  id: 'fi1',
  type: 'feature_icons',
  x_mm: 0,
  y_mm: 0,
  width_mm: 40,
  height_mm: 10,
  rotation_deg: 0,
  z_index: 1,
  locked: false,
  visible: true,
  slot_binding: null,
  text_override: null,
  props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 1.5, align: 'center' },
} as unknown as TagLayer;


describe('Inspector feature icons, fix round 1', () => {
  it('"Manage icons" asks the host to open the icon library', () => {
    const onManageIcons = vi.fn();
    render(
      <InspectorPanel
        layer={layer}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        onManageIcons={onManageIcons}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /manage icons/i }));
    expect(onManageIcons).toHaveBeenCalledTimes(1);
  });

  it('alignment is a single-choice group with the current one checked', () => {
    render(<InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
    expect(screen.getByRole('radio', { name: /^centre$/i })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: /^left$/i })).toHaveAttribute('aria-checked', 'false');
  });

  it('offers no per-layer icon order', () => {
    render(<InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={vi.fn()} onManageIcons={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /^move .* (up|down)$/i })).toBeNull();
    expect(screen.queryByText('Order')).toBeNull();
  });
});

describe('Inspector feature icons, crew pass: icons that do not fit', () => {
  const narrow = { ...layer, width_mm: 40, props: { ...layer.props, iconSize_mm: 12, gap_mm: 3 } } as TagLayer;

  it('warns how many of the icons do not fit the box', () => {
    render(<InspectorPanel layer={narrow} onUpdate={vi.fn()} onUpdateProps={vi.fn()} featureIconCount={3} />);
    expect(screen.getByRole('status')).toHaveTextContent(
      '1 of 3 icons do not fit this box. Widen the box or make the icons smaller.',
    );
  });

  it('says nothing when they all fit', () => {
    render(<InspectorPanel layer={narrow} onUpdate={vi.fn()} onUpdateProps={vi.fn()} featureIconCount={2} />);
    expect(screen.queryByText(/do not fit this box/)).toBeNull();
  });
});
