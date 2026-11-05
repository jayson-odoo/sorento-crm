/**
 * Feature icons review fix round 1: B2 the inspector opens the icon library ("Manage icons"),
 * N3 alignment is one single-choice group, and the order list moves an icon.
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
  props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 1.5, align: 'center', order: [] },
} as unknown as TagLayer;

const ICONS = [
  { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['cold_only'] },
  { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
];

describe('Inspector feature icons, fix round 1', () => {
  it('"Manage icons" asks the host to open the icon library', () => {
    const onManageIcons = vi.fn();
    render(
      <InspectorPanel
        layer={layer}
        onUpdate={vi.fn()}
        onUpdateProps={vi.fn()}
        featureIcons={ICONS}
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

  it('moving an icon down writes the whole order', () => {
    const onUpdateProps = vi.fn();
    render(
      <InspectorPanel layer={layer} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} featureIcons={ICONS} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Move Cold down' }));
    expect(onUpdateProps).toHaveBeenCalledWith('fi1', expect.objectContaining({ order: ['hot', 'cold'] }));
  });
});
