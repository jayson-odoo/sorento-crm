import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  StockBalanceRun,
  StockBalanceRunDetail,
  MirrorAnnotationPayload,
} from '../types/stockBalance.types';

const BASE = '/api/v1/inventory/stock-balance-snapshots';

export interface RunsPage {
  data: StockBalanceRun[];
  pagination: { total: number; page: number; limit: number };
}

export async function getRuns(page = 1, limit = 50): Promise<RunsPage> {
  const response = await apiFetch(`${BASE}/runs?page=${page}&limit=${limit}`);
  if (!response.ok) throw new Error('Failed to fetch stock balance runs');
  return response.json();
}

export async function getRun(runId: string): Promise<StockBalanceRunDetail> {
  const response = await apiFetch(`${BASE}/runs/${runId}`);
  if (!response.ok) throw new Error('Failed to fetch stock balance run');
  return response.json();
}

export async function annotateRun(
  runId: string,
  data: MirrorAnnotationPayload,
): Promise<StockBalanceRun> {
  const response = await apiFetch(`${BASE}/runs/${runId}/annotation`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save note'));
  }
  return response.json();
}
