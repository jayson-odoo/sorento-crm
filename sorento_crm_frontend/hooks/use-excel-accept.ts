'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

const DEFAULT_ACCEPT = '.xlsx,.xls,.xlsm';

async function fetchAccept(): Promise<string> {
  const response = await apiFetch('/api/user-management/settings');
  if (!response.ok) return DEFAULT_ACCEPT;
  const data = await response.json();
  const raw = data?.settings?.excel_upload_accept_extensions;
  if (typeof raw === 'string' && raw.trim()) return raw.trim();
  return DEFAULT_ACCEPT;
}

/** Server-configured Excel uploader accept attribute (`.xlsx,.xls[,.xlsm]`). */
export function useExcelAccept(): string {
  const { data } = useQuery({
    queryKey: ['system-settings', 'excel-accept'],
    queryFn: fetchAccept,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  return data ?? DEFAULT_ACCEPT;
}
