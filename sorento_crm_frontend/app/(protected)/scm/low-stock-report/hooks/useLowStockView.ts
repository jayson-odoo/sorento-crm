'use client';

import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getLowStockView } from '../services/lowStockReportService';
import type { LowStockRequest } from '../types/lowStockReport.types';

/** A burst of filter clicks becomes one request (AC-13). */
export const LOW_STOCK_VIEW_DEBOUNCE_MS = 250;

/**
 * The low stock report as the page shows it (PLAN-excel-preview-26sep AC-13). The request is
 * debounced, and the previous workbook stays on screen until the next one arrives
 * (`keepPreviousData`); `settling` is true from the moment the request changes until the
 * matching view is on screen, so the page can dim the grid and hold Download back - a
 * Download then would send filters the screen does not show yet.
 */
export function useLowStockView(request: LowStockRequest) {
  const key = JSON.stringify(request);
  const [debouncedKey, setDebouncedKey] = useState(key);

  useEffect(() => {
    if (key === debouncedKey) return;
    const timer = window.setTimeout(() => setDebouncedKey(key), LOW_STOCK_VIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [key, debouncedKey]);

  const query = useQuery({
    queryKey: ['scm', 'low-stock-report', 'view', debouncedKey] as const,
    queryFn: () => getLowStockView(JSON.parse(debouncedKey) as LowStockRequest),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

  return {
    ...query,
    /** The request the view on screen answers - what Download must send. */
    shownRequest: JSON.parse(debouncedKey) as LowStockRequest,
    settling: key !== debouncedKey || query.isPlaceholderData,
  };
}
