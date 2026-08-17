'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

const DEFAULT_CURRENCY_FORMAT = 'RM {value}';

/**
 * The system currency format string (e.g. "RM {value}") from the singleton
 * system settings. Feed it into `formatCurrency(value, currencyFormat)`.
 *
 * Reads the narrow `/settings/app-config` projection, not the full settings
 * blob: that one is gated on `user_management.settings.view`, which the roles
 * on the screens rendering currency do not hold. The projection is flat, so
 * `currency_format` sits at the top level rather than under `settings`.
 *
 * Cached under its own key with an infinite staleTime — the value changes only
 * when an admin saves Settings → General. Falls back to the shipped default
 * while loading or if the endpoint is unreachable.
 */
export function useCurrencyFormat(): string {
  const { data } = useQuery({
    queryKey: ['system-app-config', 'currency-format'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/settings/app-config');
      if (!response.ok) throw new Error('Failed to fetch settings');
      const data = await response.json();
      const fmt = data?.currency_format;
      return typeof fmt === 'string' && fmt.trim() ? fmt : DEFAULT_CURRENCY_FORMAT;
    },
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  return data ?? DEFAULT_CURRENCY_FORMAT;
}
