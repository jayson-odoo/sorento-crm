/**
 * The promotion filter's option source.
 *
 * It was an inline closure in the picker, so its identity changed on every
 * parent render - a keystroke in the product search box - and SearchableSelect
 * refetched a page of promotions each time the popover happened to be open.
 */
import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../services/brochureImageService', () => ({
  BROCHURE_IMAGE_PAGE_SIZE: 25,
  PROMOTION_PAGE_SIZE: 50,
  listBrochureImages: vi.fn(),
  listBrochureImagePromotionOptions: vi.fn(),
}));

import { listBrochureImagePromotionOptions } from '../../services/brochureImageService';
import { useBrochureImagePromotionOptions } from './useBrochureImages';

const mockPromotions = vi.mocked(listBrochureImagePromotionOptions);

beforeEach(() => {
  vi.clearAllMocks();
  mockPromotions.mockResolvedValue([]);
});

describe('useBrochureImagePromotionOptions', () => {
  it('hands out the same fetcher on every render', () => {
    const seen: unknown[] = [];

    function Probe() {
      const { fetchOptions } = useBrochureImagePromotionOptions();
      seen.push(fetchOptions);
      return null;
    }

    const { rerender } = render(<Probe />);
    rerender(<Probe />);

    expect(seen).toHaveLength(2);
    expect(seen[0]).toBe(seen[1]);
  });

  it('goes through the service for a page of promotions', async () => {
    mockPromotions.mockResolvedValue([{ value: 'promo-1', label: 'A3 Flyer 2026' }]);
    let fetchOptions!: (query: string, pageIndex: number) => Promise<unknown[]>;

    function Probe() {
      fetchOptions = useBrochureImagePromotionOptions().fetchOptions;
      return null;
    }
    render(<Probe />);

    await expect(fetchOptions('flyer', 1)).resolves.toEqual([
      { value: 'promo-1', label: 'A3 Flyer 2026' },
    ]);
    expect(mockPromotions).toHaveBeenCalledWith('flyer', 1);
  });

  it('remembers a promotion it has already shown, so the trigger never falls back to an id', async () => {
    mockPromotions.mockResolvedValue([{ value: 'promo-1', label: 'A3 Flyer 2026' }]);
    let hook!: ReturnType<typeof useBrochureImagePromotionOptions>;

    function Probe() {
      hook = useBrochureImagePromotionOptions();
      return null;
    }
    render(<Probe />);

    expect(hook.optionFor('promo-1')).toBeUndefined();
    await hook.fetchOptions('', 0);
    expect(hook.optionFor('promo-1')).toEqual({ value: 'promo-1', label: 'A3 Flyer 2026' });
  });
});
