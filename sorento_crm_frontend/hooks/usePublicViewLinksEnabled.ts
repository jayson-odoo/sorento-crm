'use client';

import { useMemo } from 'react';
import { useTenantModules } from '@/hooks/useTenantModules';

const PUBLIC_VIEW_LINKS_KEY = 'public_view_links';

/**
 * True when tenant modules are unknown (loading) or public_view_links is enabled in App Store.
 * When modules are loaded and the feature is off, returns false — hide copy/attach view link UI.
 */
export function usePublicViewLinksEnabled(): boolean {
  const { enabledModuleKeys } = useTenantModules();
  return useMemo(
    () => !enabledModuleKeys || enabledModuleKeys.has(PUBLIC_VIEW_LINKS_KEY),
    [enabledModuleKeys],
  );
}
