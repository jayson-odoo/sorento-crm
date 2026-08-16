'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

const DEFAULT_ACCEPT = '.xlsx,.xls,.xlsm';

/**
 * `excel_upload_accept_extensions` is NOT a column on the backend SystemSetting
 * model and never has been, so this has always returned DEFAULT_ACCEPT. The
 * fallback is the real behaviour, not a symptom of moving off the full settings
 * blob onto the narrow `/settings/app-config` projection. Deliberately not added
 * to that projection; if the setting is ever wanted, it needs a column first.
 */
async function fetchAccept(): Promise<string> {
  const response = await apiFetch('/api/user-management/settings/app-config');
  if (!response.ok) return DEFAULT_ACCEPT;
  const data = await response.json();
  const raw = data?.excel_upload_accept_extensions;
  if (typeof raw === 'string' && raw.trim()) return raw.trim();
  return DEFAULT_ACCEPT;
}

/** Server-configured Excel uploader accept attribute (`.xlsx,.xls[,.xlsm]`). */
export function useExcelAccept(): string {
  const { data } = useQuery({
    queryKey: ['system-app-config', 'excel-accept'],
    queryFn: fetchAccept,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  return data ?? DEFAULT_ACCEPT;
}
