import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QtyOverQuoteDialog } from './QtyOverQuoteDialog';
import type { QtyOverProduct } from '../lib/qtyOverQuote';

const products: QtyOverProduct[] = [
  { product_code: 'SKU-1', description: 'Tile one', ordered: '12.000', quoted: '10.000' },
  { product_code: null, description: 'Grout', ordered: '5', quoted: '2' },
];

function setup(over: Partial<React.ComponentProps<typeof QtyOverQuoteDialog>> = {}) {
  const onCancel = vi.fn();
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(
    <QtyOverQuoteDialog
      products={products}
      isSaving={false}
      onCancel={onCancel}
      onSubmit={onSubmit}
      {...over}
    />,
  );
  return { onCancel, onSubmit };
}

describe('QtyOverQuoteDialog', () => {
  it('says one plain line per product: ordered and quoted', () => {
    setup();
    expect(screen.getByText('SKU-1: 12 ordered, 10 quoted.')).toBeInTheDocument();
    expect(screen.getByText('Grout: 5 ordered, 2 quoted.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('keeps Save disabled until the reason is non-blank', () => {
    setup();
    const save = screen.getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: '   ' } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Customer asked' } });
    expect(save).toBeEnabled();
  });

  it('submits the trimmed reason', () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: '  Extra stock  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSubmit).toHaveBeenCalledWith('Extra stock');
  });

  it('Cancel calls onCancel', () => {
    const { onCancel, onSubmit } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('is disabled while saving', () => {
    setup({ isSaving: true });
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'x' } });
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
  });

  it('renders nothing when products is null', () => {
    setup({ products: null });
    expect(screen.queryByText('More than quoted')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });
});
