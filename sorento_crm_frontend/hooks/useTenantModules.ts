'use client';

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import {
  fetchMyModules,
  type MyModulesPayload,
} from '@/app/(protected)/system-management/app-store/services/appModulesService';

export const TENANT_MODULES_QUERY_KEY = ['tenant-modules'] as const;

export function useTenantModules() {
  const query = useQuery({
    queryKey: TENANT_MODULES_QUERY_KEY,
    queryFn: fetchMyModules,
    staleTime: 60_000,
    retry: 1,
  });

  const enabledModuleKeys = useMemo(() => {
    if (!query.data?.modules) return null;
    const set = new Set<string>();
    for (const m of query.data.modules) {
      if (m.enabled) set.add(m.module_key);
    }
    return set;
  }, [query.data?.modules]);

  return {
    ...query,
    enabledModuleKeys,
    moduleGuardStrict: query.data?.module_guard_strict ?? false,
    raw: query.data as MyModulesPayload | undefined,
  };
}
