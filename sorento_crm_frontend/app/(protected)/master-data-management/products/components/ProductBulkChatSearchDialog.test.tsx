/**
 * The one bulk action for the chat-search flag (#300): both directions go
 * through the same dialog and the same PUT /products/bulk, carrying the count.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

const mutate = vi.fn();

vi.mock('../hooks/useProducts', () => ({
  useBulkUpdateProducts: () => ({ mutate, isPending: false }),
}));

import ProductBulkChatSearchDialog from './ProductBulkChatSearchDialog';

describe('ProductBulkChatSearchDialog', () => {
  beforeEach(() => mutate.mockReset());
  afterEach(() => cleanup());

  it('names the selection count and hides the selected products', () => {
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    render(
      <ProductBulkChatSearchDialog
        open
        onOpenChange={onOpenChange}
        productIds={['a', 'b', 'c']}
        onSuccess={onSuccess}
      />,
    );

    expect(screen.getByText('Chat search for 3 products')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Hide from chat' }));

    expect(mutate).toHaveBeenCalledTimes(1);
    const [payload, options] = mutate.mock.calls[0];
    expect(payload).toEqual({ ids: ['a', 'b', 'c'], updates: { is_searchable: false } });

    options.onSuccess();
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('shows the selected products again through the same action', () => {
    render(
      <ProductBulkChatSearchDialog open onOpenChange={vi.fn()} productIds={['a']} />,
    );

    expect(screen.getByText('Chat search for 1 product')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show in chat' }));

    expect(mutate.mock.calls[0][0]).toEqual({ ids: ['a'], updates: { is_searchable: true } });
  });

  it('does nothing with an empty selection', () => {
    render(<ProductBulkChatSearchDialog open onOpenChange={vi.fn()} productIds={[]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Hide from chat' }));
    expect(mutate).not.toHaveBeenCalled();
  });
});
