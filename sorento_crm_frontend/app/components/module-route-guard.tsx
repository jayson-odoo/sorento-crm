'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useTenantModules } from '@/hooks/useTenantModules';
import { moduleKeyForPath } from '@/lib/route-module-map';

/**
 * When tenant modules are loaded, redirect away from routes whose module is disabled.
 * Fail-open while loading or on fetch error (enabledModuleKeys === null).
 */
export function ModuleRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { enabledModuleKeys, isLoading, isError } = useTenantModules();

  useEffect(() => {
    if (isLoading || isError) return;
    if (!enabledModuleKeys) return;
    const key = moduleKeyForPath(pathname || '/');
    if (!key) return;
    if (!enabledModuleKeys.has(key)) {
      router.replace('/');
    }
  }, [pathname, enabledModuleKeys, isLoading, isError, router]);

  return <>{children}</>;
}
