/**
 * The currencies the cost lists are priced in: ONE list for the cost-price upload, the cost row
 * dialog and the Costing exchange-rate form (which also offers any other code a cost row already
 * uses, from `GET /costing/currencies`). The ringgit is the base currency and has no rate.
 */
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

export const BASE_CURRENCY = 'MYR';

export const COST_CURRENCIES: readonly { code: string; name: string }[] = [
  { code: 'CNY', name: 'Chinese yuan' },
  { code: 'USD', name: 'US dollar' },
  { code: 'MYR', name: 'Malaysian ringgit' },
  { code: 'EUR', name: 'Euro' },
];

/** "CNY, Chinese yuan": the upload dialog's list. */
export const CURRENCY_NAMED_OPTIONS: SearchableSelectOption[] = COST_CURRENCIES.map((c) => ({
  value: c.code,
  label: `${c.code}, ${c.name}`,
}));

/** "CNY": the cost row dialog's list. */
export const CURRENCY_CODE_OPTIONS: SearchableSelectOption[] = COST_CURRENCIES.map((c) => ({
  value: c.code,
  label: c.code,
}));

/** The codes a rate can be set for without asking the server: every one but the ringgit. */
export const FOREIGN_CURRENCY_CODES: string[] = COST_CURRENCIES.filter((c) => c.code !== BASE_CURRENCY).map(
  (c) => c.code,
);
