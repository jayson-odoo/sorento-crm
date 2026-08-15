/**
 * usePlanLines - the purchase-trend fetch is LAZY (Fix 5, 2026-08-12), unlike every
 * other fetch this hook merges. Eagerly fetching it for every product on plan mount
 * was pure waste: the PO cell's popover is the only place it is read, and most rows on
 * a plan never have that popover opened. `requestPurchaseTrend()` flips a "wanted"
 * flag once the first popover opens; react-query caches the response the normal way
 * after that, so a second popover on the same run is free.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getBuyRecommendationsForCash = vi.fn();
const getCoveredRecommendations = vi.fn();
const getNeedsLevelRecommendations = vi.fn();
const getAllDispositionRecommendations = vi.fn();
const getCoverSources = vi.fn();
const getPriceHistory = vi.fn();
const getTrajectory = vi.fn();
const getLevelSuggestions = vi.fn();
const getPurchaseTrend = vi.fn();
const getPoBook = vi.fn();
const getProductEconomics = vi.fn();
const getProductImages = vi.fn();
const amendLevelSuggestion = vi.fn();
const recordLifecycleDecision = vi.fn();

vi.mock('../services/reorderRunService', () => ({
  getBuyRecommendationsForCash: (...a: unknown[]) => getBuyRecommendationsForCash(...a),
  getCoveredRecommendations: (...a: unknown[]) => getCoveredRecommendations(...a),
  getNeedsLevelRecommendations: (...a: unknown[]) => getNeedsLevelRecommendations(...a),
  getAllDispositionRecommendations: (...a: unknown[]) => getAllDispositionRecommendations(...a),
  getCoverSources: (...a: unknown[]) => getCoverSources(...a),
  getPriceHistory: (...a: unknown[]) => getPriceHistory(...a),
  getTrajectory: (...a: unknown[]) => getTrajectory(...a),
  getLevelSuggestions: (...a: unknown[]) => getLevelSuggestions(...a),
  getPurchaseTrend: (...a: unknown[]) => getPurchaseTrend(...a),
  getPoBook: (...a: unknown[]) => getPoBook(...a),
  getProductEconomics: (...a: unknown[]) => getProductEconomics(...a),
  getProductImages: (...a: unknown[]) => getProductImages(...a),
  amendLevelSuggestion: (...a: unknown[]) => amendLevelSuggestion(...a),
  recordLifecycleDecision: (...a: unknown[]) => recordLifecycleDecision(...a),
}));

import { usePlanLines } from './usePlanLines';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  getBuyRecommendationsForCash.mockReset().mockResolvedValue([]);
  getCoveredRecommendations.mockReset().mockResolvedValue([]);
  getNeedsLevelRecommendations.mockReset().mockResolvedValue([]);
  getAllDispositionRecommendations.mockReset().mockResolvedValue([]);
  getCoverSources.mockReset().mockResolvedValue({});
  getPriceHistory.mockReset().mockResolvedValue({ prices: {}, movement_threshold_pct: 5, stale_after_days: 180 });
  getTrajectory.mockReset().mockResolvedValue({ series: {} });
  getLevelSuggestions.mockReset().mockResolvedValue({ suggestions: {} });
  getPurchaseTrend.mockReset().mockResolvedValue({ window_months: 3, products: {} });
  getPoBook.mockReset().mockResolvedValue({ po_book: {} });
  getProductEconomics.mockReset().mockResolvedValue({ products: {}, thresholds: {} });
  getProductImages.mockReset().mockResolvedValue({ has_image: {} });
});

describe('usePlanLines - purchase trend is lazy, not eager', () => {
  it('does NOT fetch the purchase trend on mount, even though every other fetch runs', async () => {
    renderHook(() => usePlanLines('run-1', true), { wrapper });

    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalledWith('run-1'));
    expect(getCoveredRecommendations).toHaveBeenCalledWith('run-1');
    expect(getNeedsLevelRecommendations).toHaveBeenCalledWith('run-1');
    expect(getAllDispositionRecommendations).toHaveBeenCalledWith('run-1');
    expect(getPurchaseTrend).not.toHaveBeenCalled();
  });

  it('fetches the purchase trend once requestPurchaseTrend() is called', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());
    expect(getPurchaseTrend).not.toHaveBeenCalled();

    act(() => result.current.requestPurchaseTrend());

    await waitFor(() => expect(getPurchaseTrend).toHaveBeenCalledWith('run-1'));
  });

  it('never re-fetches on a second requestPurchaseTrend() call - the cached response stands', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    act(() => result.current.requestPurchaseTrend());
    await waitFor(() => expect(getPurchaseTrend).toHaveBeenCalledTimes(1));

    act(() => result.current.requestPurchaseTrend());
    expect(getPurchaseTrend).toHaveBeenCalledTimes(1);
  });

  it('never fetches the purchase trend at all when the run is disabled', () => {
    renderHook(() => usePlanLines(null, false), { wrapper });
    expect(getPurchaseTrend).not.toHaveBeenCalled();
    expect(getBuyRecommendationsForCash).not.toHaveBeenCalled();
  });
});

describe('usePlanLines - the photo map is lazy too, and one call for the whole run (AC-7)', () => {
  it('does NOT fetch the photos on mount', async () => {
    renderHook(() => usePlanLines('run-1', true), { wrapper });

    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalledWith('run-1'));
    expect(getProductImages).not.toHaveBeenCalled();
  });

  it('fetches them once, on the first icon opened, however many rows ask', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    act(() => result.current.requestProductImages());
    await waitFor(() => expect(getProductImages).toHaveBeenCalledWith('run-1'));

    act(() => result.current.requestProductImages());
    expect(getProductImages).toHaveBeenCalledTimes(1);
  });

  it('reports idle until asked, then ready, and says which products have a photo', async () => {
    getProductImages.mockResolvedValue({ has_image: { p1: true } });
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    expect(result.current.photoStatus).toBe('idle');

    act(() => result.current.requestProductImages());
    await waitFor(() => expect(result.current.photoStatus).toBe('ready'));

    const withPhoto = { product_id: 'p1' } as never;
    const without = { product_id: 'p2' } as never;
    expect(result.current.hasPhotoFor(withPhoto)).toBe(true);
    expect(result.current.hasPhotoFor(without)).toBe(false);
  });

  it('a failed photo fetch is reported, and never takes the plan down with it', async () => {
    getProductImages.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    act(() => result.current.requestProductImages());

    await waitFor(() => expect(result.current.photoStatus).toBe('error'));
    expect(result.current.isError).toBe(false);
  });
});
