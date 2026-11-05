/**
 * PRICETAG-COMBO-RENDER AC-A3: a text layer bound to a price slot offers the price badge's
 * "Show currency" checkbox, off by default; any other text layer does not.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

function textLayer(slot: string | null): TagLayer {
  return {
    id: 't1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: slot,
    text_override: null,
    props: {
      kind: 'text',
      text: '',
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
    },
  } as unknown as TagLayer;
}

describe('Inspector Show currency on a text price', () => {
  it.each(['list_price', 'sell_price', 'price'])('is offered for %s and sets showCurrency', (slot) => {
    const onUpdateProps = vi.fn();
    render(<InspectorPanel layer={textLayer(slot)} onUpdate={vi.fn()} onUpdateProps={onUpdateProps} />);
    const box = screen.getByRole('checkbox', { name: /show currency/i });
    expect(box).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(box);
    expect(onUpdateProps).toHaveBeenCalledWith('t1', expect.objectContaining({ showCurrency: true }));
  });

  it('is not offered for a code slot or an unbound text layer', () => {
    for (const slot of ['code', null]) {
      const { unmount } = render(
        <InspectorPanel layer={textLayer(slot)} onUpdate={vi.fn()} onUpdateProps={vi.fn()} />,
      );
      expect(screen.queryByRole('checkbox', { name: /show currency/i })).toBeNull();
      unmount();
    }
  });
});
