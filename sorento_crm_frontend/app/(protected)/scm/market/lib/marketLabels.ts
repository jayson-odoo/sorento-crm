/**
 * Static option lists + label resolvers for the market advisory UI. Currency and
 * cadence are small closed sets (static SearchableSelect options); category
 * resolves against the live product-category options so a stored `category_ref`
 * renders as a readable label, never a UUID.
 */
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type { MarketCadence, MarketTrend } from '../types/market.types';

/** Cadence choices for a research topic (M5-D6). */
export const CADENCE_OPTIONS: SearchableSelectOption[] = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'manual', label: 'Manual only' },
];

export const CADENCE_LABEL: Record<MarketCadence, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  manual: 'Manual only',
};

/** Common trade currencies (static - no dedicated currency endpoint). */
export const CURRENCY_OPTIONS: SearchableSelectOption[] = [
  { value: 'MYR', label: 'MYR - Malaysian Ringgit' },
  { value: 'USD', label: 'USD - US Dollar' },
  { value: 'EUR', label: 'EUR - Euro' },
  { value: 'CNY', label: 'CNY - Chinese Yuan' },
  { value: 'JPY', label: 'JPY - Japanese Yen' },
  { value: 'SGD', label: 'SGD - Singapore Dollar' },
];

/**
 * Trend presentation. For COST/price signals `up` is adverse (cost rising) so it
 * takes the stockout/red treatment; `down` is favourable (green); `flat`/null are
 * neutral. Colours reuse the SCM health palette.
 */
export const TREND_META: Record<
  'up' | 'down' | 'flat' | 'unknown',
  { label: string; textClass: string; softBgClass: string }
> = {
  up: { label: 'Rising', textClass: 'text-scm-stockout', softBgClass: 'bg-scm-stockout-soft' },
  down: { label: 'Falling', textClass: 'text-scm-healthy', softBgClass: 'bg-scm-healthy-soft' },
  flat: { label: 'Flat', textClass: 'text-muted-foreground', softBgClass: 'bg-muted' },
  unknown: { label: 'Unknown', textClass: 'text-muted-foreground', softBgClass: 'bg-muted' },
};

export function trendKey(trend: MarketTrend): 'up' | 'down' | 'flat' | 'unknown' {
  return trend ?? 'unknown';
}

/**
 * Resolve a stored `category_ref` to a readable label using the loaded category
 * options (value = category id). Falls back to the ref itself when it is not a
 * known option value (mock seeds use readable codes), so a UUID never leaks.
 */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function resolveCategoryLabel(
  ref: string | null,
  options: SearchableSelectOption[] | undefined,
): string | null {
  if (!ref) return null;
  const match = options?.find((o) => o.value === ref);
  if (match) return match.label;
  // Never surface a raw UUID (e.g. before options load) - show a neutral
  // placeholder; a readable code ref falls through unchanged.
  return UUID_RE.test(ref) ? 'Category' : ref;
}
