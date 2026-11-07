/** O1: Insert field lists the previewed combo's positions under "Combo positions". */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagBindingData } from '@/lib/dealer-kit/tag-template-types';
import { InsertFieldDialog } from './InsertFieldDialog';

const part = (code: string) => ({
  product_id: code, code, name: code, dimensions: '', list_price: 1, sell_price: null, images: [],
});

function open(data: TagBindingData | null) {
  const onDone = vi.fn();
  render(
    <InsertFieldDialog open value="" data={data} specKeys={[]} onCancel={vi.fn()} onDone={onDone} />,
  );
  return onDone;
}

describe('Insert field, Combo positions', () => {
  it('names the previewed combo positions with their codes and inserts the token', () => {
    const data = {
      kind: 'product',
      product: {
        id: 'p', code: 'HOST', name: 'Host', dimensions: '', spec_lines: [], specs: [], images: [],
        list_price: 1, offer_price: null, promotion_id: null, barcode: null,
        slots: { fixed: [part('FIX1')], groups: [{ role: 'Tap colour', size: 2, picks: [part('PA'), part('PB')] }], upgrades: [] },
      },
    } as unknown as TagBindingData;
    const onDone = open(data);
    expect(screen.getByText('Combo positions')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Tap colour, pick 2 code: PB'));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith('{{slot.pick.1.2.code}}');
  });

  it('falls back to the generic position counts with no combo previewed', () => {
    open(null);
    expect(screen.getByText('Fixed part 4 code')).toBeInTheDocument();
    expect(screen.queryByText('Fixed part 5 code')).toBeNull();
  });
});
