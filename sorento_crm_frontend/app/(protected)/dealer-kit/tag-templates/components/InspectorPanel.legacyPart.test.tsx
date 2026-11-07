/** PRICETAG-COMBO-RENDER fix round 1: a legacy numeric subjectPart stays visible in the template editor. */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ value, options }: { value: string; options: { value: string; label: string }[] }) => (
    <select data-testid="product-select" value={value} onChange={() => undefined}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import type { TagLayer, TagLayerProps } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const layer = (props: Record<string, unknown>) =>
  ({
    id: 'l1', type: 'text', x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 12, rotation_deg: 0, z_index: 1,
    locked: false, visible: true, slot_binding: 'code', text_override: null,
    props: { kind: 'text', text: 'Code', ...props } as TagLayerProps,
  }) as TagLayer;

function productSelect() {
  const section = screen.getByRole('heading', { level: 4, name: 'Product' }).closest('section')!;
  return section.querySelector('select') as HTMLSelectElement;
}

describe('a layer with a legacy part number in the template editor', () => {
  it('shows it as "Part n" and keeps it selected', () => {
    const Panel = InspectorPanel as unknown as React.ComponentType<Record<string, unknown>>;
    render(<Panel layer={layer({ subjectPart: 1 })} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />);
    expect(productSelect().value).toBe('1');
    expect(productSelect().selectedOptions[0].textContent).toBe('Part 2');
  });

  it('shows no such option once the layer reads a position', () => {
    const Panel = InspectorPanel as unknown as React.ComponentType<Record<string, unknown>>;
    render(
      <Panel layer={layer({ subjectPart: 1, subjectSlot: { kind: 'main' } })} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />,
    );
    expect(productSelect().value).toBe('slot:main');
    expect([...productSelect().options].some((o) => o.textContent === 'Part 2')).toBe(false);
  });
});
