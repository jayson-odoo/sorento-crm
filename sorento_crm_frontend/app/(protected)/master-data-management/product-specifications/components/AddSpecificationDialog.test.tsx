/**
 * AC-A.5, AC-G.8 - Add a specification: label, type, unit, slug preview, the
 * near-duplicate warning, and the create-then-navigate round trip.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const createSpecKey = vi.fn();
const getSimilarSpecKey = vi.fn();
vi.mock('../services/productSpecService', () => ({
  createSpecKey: (...a: unknown[]) => createSpecKey(...a),
  getSimilarSpecKey: (...a: unknown[]) => getSimilarSpecKey(...a),
  rereadCatalogue: vi.fn(),
}));

import { AddSpecificationDialog } from './AddSpecificationDialog';

function renderDialog(onCreated = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <AddSpecificationDialog open onOpenChange={onOpenChange} onCreated={onCreated} />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange, onCreated };
}

beforeEach(() => {
  cleanup();
  createSpecKey.mockReset();
  getSimilarSpecKey.mockReset();
  getSimilarSpecKey.mockResolvedValue(null);
});

describe('AddSpecificationDialog', () => {
  it('previews the slug under the label as it is typed', async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText('Label'), {
      target: { value: 'Rough-in distance' },
    });
    expect(await screen.findByText('rough_in_distance')).toBeInTheDocument();
  });

  it('renders the near-duplicate warning as the label is typed, before any submit', async () => {
    getSimilarSpecKey.mockResolvedValue({
      spec_key: 'brand',
      label: 'Brand',
      matched_on: 'label',
      matched_text: 'Brand',
    });
    renderDialog();

    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Brand' } });

    expect(await screen.findByText(/Brand already exists/i)).toBeInTheDocument();
    expect(getSimilarSpecKey).toHaveBeenCalledWith('Brand');
    expect(createSpecKey).not.toHaveBeenCalled();
  });

  it('checks for a near-duplicate before creating, and offers it instead', async () => {
    getSimilarSpecKey.mockResolvedValue({
      spec_key: 'finish',
      label: 'Finish',
      matched_on: 'label',
      matched_text: 'Finish',
    });
    renderDialog();

    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Finish' } });
    fireEvent.click(screen.getByRole('button', { name: /^Add specification$/i }));

    expect(await screen.findByText(/Finish already exists/i)).toBeInTheDocument();
    expect(createSpecKey).not.toHaveBeenCalled();
  });

  it('creates the specification and hands the new slug back', async () => {
    createSpecKey.mockResolvedValue({ spec_key: 'rough_in_distance', label: 'Rough-in distance' });
    const onCreated = vi.fn();
    renderDialog(onCreated);

    fireEvent.change(screen.getByLabelText('Label'), {
      target: { value: 'Rough-in distance' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Add specification$/i }));

    await waitFor(() =>
      expect(createSpecKey).toHaveBeenCalledWith(
        expect.objectContaining({ spec_key: 'rough_in_distance', label: 'Rough-in distance' }),
      ),
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('rough_in_distance'));
  });
});
