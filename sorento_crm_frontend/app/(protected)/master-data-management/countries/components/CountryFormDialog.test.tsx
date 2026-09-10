/**
 * CountryFormDialog - the Add/Edit modal's own validation (S1, `PLAN-local-supplier-oi-
 * routing.md`, AC-1.9): an empty or non-2-letter code shows a message and submits nothing.
 *
 * The mutation hooks are mocked so a rejected submit is provable by "the mutation was never
 * called", not by a network assertion.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mutateAsync = vi.fn();
vi.mock('../hooks/useCountries', () => ({
  useCreateCountry: () => ({ mutateAsync, isPending: false }),
  useUpdateCountry: () => ({ mutateAsync, isPending: false }),
}));

import CountryFormDialog from './CountryFormDialog';

beforeEach(() => {
  vi.clearAllMocks();
});

function renderDialog() {
  return render(
    <CountryFormDialog open onOpenChange={vi.fn()} country={null} />,
  );
}

describe('CountryFormDialog', () => {
  it('rejects an empty code and submits nothing', async () => {
    renderDialog();

    fireEvent.change(screen.getByPlaceholderText('Malaysia'), {
      target: { value: 'Atlantis' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));

    expect(await screen.findByText(/code must be exactly 2 letters/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('rejects a non-2-letter code and submits nothing', async () => {
    renderDialog();

    fireEvent.change(screen.getByPlaceholderText('MY'), { target: { value: 'MYS' } });
    fireEvent.change(screen.getByPlaceholderText('Malaysia'), {
      target: { value: 'Malaysia' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));

    expect(await screen.findByText(/code must be exactly 2 letters/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('accepts a valid 2-letter code and submits', async () => {
    renderDialog();

    fireEvent.change(screen.getByPlaceholderText('MY'), { target: { value: 'my' } });
    fireEvent.change(screen.getByPlaceholderText('Malaysia'), {
      target: { value: 'Malaysia' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'MY', name: 'Malaysia' }),
      ),
    );
  });
});
