/**
 * N-11 (review round 2) - Try a phrase reads like the rest of the spec screens:
 * values as words ("Rose gold", "Yes"), keys as words, no ranking score and no
 * model name.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const previewSpecSearch = vi.fn();
vi.mock('../services/productSpecService', () => ({
  previewSpecSearch: (...a: unknown[]) => previewSpecSearch(...a),
}));

import { TryPhraseDialog } from './TryPhraseDialog';

describe('N-11 - Try a phrase shows readable values, no score, no model name', () => {
  it('reads keys and values as words, and never prints the score or the model', async () => {
    previewSpecSearch.mockResolvedValue({
      candidates: [
        {
          product_id: 'p1',
          product_code: 'WC100',
          summary: 'Rose gold basin',
          class: null,
          matched_specs: ['capacity_oz'],
          score: 12.5,
          is_discontinued: false,
        },
      ],
      floor_missed: false,
      top_score: 12.5,
      floor: 5,
      understanding: {
        source: 'semantic',
        model: 'gpt-4o-mini',
        elapsed_ms: 120,
        specs: [
          { key: 'finish_colour', value: 'rose_gold' },
          { key: 'is_smart', value: true },
        ],
        exclusions: [{ key: 'from_category', value: 'one_piece' }],
        free_terms: [],
        notes: '',
      },
      unmet: [{ key: 'finish_colour', value: 'matt_black' }],
    });
    render(<TryPhraseDialog open onOpenChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Customer phrase'), { target: { value: 'rose gold smart basin' } });
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    await screen.findByText('WC100');

    const text = document.body.textContent ?? '';
    expect(text).toContain('Rose gold');
    expect(text).toContain('Yes');
    expect(text).toContain('One piece');
    expect(text).toContain('Matt black');
    expect(text).not.toContain('gpt-4o-mini');
    expect(text).not.toContain('12.5');
    expect(text).not.toMatch(/\w_\w/);
    expect(text).not.toMatch(/\btrue\b/);
  });
});
