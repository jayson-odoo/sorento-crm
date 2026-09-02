/**
 * AC-A.6, AC-G.8 - Try a phrase: the empty result, and that the last run
 * survives the dialog closing (state stays on the component, not the URL).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

const previewSpecSearch = vi.fn();
vi.mock('../services/productSpecService', () => ({
  previewSpecSearch: (...a: unknown[]) => previewSpecSearch(...a),
}));

import { TryPhraseDialog } from './TryPhraseDialog';

beforeEach(() => {
  cleanup();
  previewSpecSearch.mockReset();
});

describe('TryPhraseDialog', () => {
  it('says no product matched, with the phrase echoed', async () => {
    previewSpecSearch.mockResolvedValue({
      candidates: [],
      floor_missed: true,
      top_score: 0,
      floor: 5,
      understanding: null,
      unmet: [],
    });
    render(<TryPhraseDialog open onOpenChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Customer phrase'), {
      target: { value: 'quantum toaster' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));

    expect(await screen.findByText(/No product matched “quantum toaster”/)).toBeInTheDocument();
  });

  it('keeps the last run when the dialog is re-opened', async () => {
    previewSpecSearch.mockResolvedValue({
      candidates: [
        {
          product_id: 'p1',
          product_code: 'WC-100',
          summary: 'chrome finish',
          class: null,
          matched_specs: ['finish'],
          score: 12,
          is_discontinued: false,
        },
      ],
      floor_missed: false,
      top_score: 12,
      floor: 5,
      understanding: null,
      unmet: [],
    });
    const { rerender } = render(<TryPhraseDialog open onOpenChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Customer phrase'), {
      target: { value: 'chrome finish' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    expect(await screen.findByText('WC-100')).toBeInTheDocument();

    // Close, then re-open: the component instance stays mounted (the page hosts
    // it once), so the last result is still here without a second search.
    rerender(<TryPhraseDialog open={false} onOpenChange={vi.fn()} />);
    rerender(<TryPhraseDialog open onOpenChange={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('WC-100')).toBeInTheDocument());
    expect(previewSpecSearch).toHaveBeenCalledTimes(1);
  });
});
