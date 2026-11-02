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
  it('renders each product with its ordered and quoted quantity', () => {
    setup();
    expect(screen.getByText('SKU-1')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('Grout')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('keeps Save with reason disabled until the reason is non-blank', () => {
    setup();
    const save = screen.getByRole('button', { name: 'Save with reason' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: '   ' } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Customer asked' } });
    expect(save).toBeEnabled();
  });

  it('submits the trimmed reason', () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: '  Extra stock  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save with reason' }));
    expect(onSubmit).toHaveBeenCalledWith('Extra stock');
  });

  it('Back calls onCancel', () => {
    const { onCancel, onSubmit } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
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
    expect(screen.queryByText('Quantity over the quotation')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save with reason' })).toBeNull();
  });
});
