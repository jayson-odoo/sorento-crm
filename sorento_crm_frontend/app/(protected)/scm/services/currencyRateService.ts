/**
 * ============================================================================
 * SCM exchange rates - what makes two supplier prices comparable
 * ============================================================================
 * Layering: CurrencyRatesPanel -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/config.py) ────────────────────────────
 *
 *  GET    /api/v1/scm/config/currency-rates             -> 200 CurrencyRates
 *  PUT    /api/v1/scm/config/currency-rates/{currency}  -> 200 { action, rate }
 *  DELETE /api/v1/scm/config/currency-rates/{currency}  -> 204
 *
 * Read is gated on `scm.dashboard.view`, writes on `scm.config.manage`.
 *
 * `missing` is the reason this screen exists rather than being a settings page
 * nobody visits: it lists the currencies the purchase-order book actually
 * prices in that have no rate, so the buyer is TOLD which rate to add instead
 * of deducing it from a plan row that quietly refuses to fund.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface CurrencyRate {
  /** ISO code, upper case. The base currency never appears: its rate is 1. */
  currency: string;
  /** What one unit of `currency` is worth in the base currency. */
  rate_to_base: number;
  /** When the rate was true. Shown so an old rate reads as an old rate. */
  as_of: string | null;
  note: string | null;
  updated_at: string | null;
}

export interface CurrencyRates {
  base_currency: string;
  rates: CurrencyRate[];
  /** Currencies the book prices in with no rate on file. Each one is a plan that
   *  cannot rank or fund those suppliers until somebody enters a number. */
  missing: string[];
}

export interface CurrencyRateWrite {
  rate_to_base: number;
  as_of: string | null;
  note: string | null;
}

async function readJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

export async function getCurrencyRates(): Promise<CurrencyRates> {
  const res = await apiFetch('/api/v1/scm/config/currency-rates');
  return readJson<CurrencyRates>(res, 'Failed to load exchange rates');
}

export async function saveCurrencyRate(
  currency: string,
  body: CurrencyRateWrite,
): Promise<void> {
  const res = await apiFetch(
    `/api/v1/scm/config/currency-rates/${encodeURIComponent(currency)}`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the rate'));
}

export async function deleteCurrencyRate(currency: string): Promise<void> {
  const res = await apiFetch(
    `/api/v1/scm/config/currency-rates/${encodeURIComponent(currency)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove the rate'));
}
