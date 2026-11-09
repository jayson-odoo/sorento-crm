'use client';

import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';

import { usePermissions } from '@/hooks/usePermissions';
import { FEATURE_ICONS_KEY, kitLibraryClient } from '@/lib/dealer-kit/kit-library-cache';
import { iconsForSpecValue } from '@/lib/dealer-kit/feature-icons';
import {
  listFeatureIcons,
  type FeatureIconWithUrl,
} from '@/app/(protected)/dealer-kit/services/tagDataService';
import type { SpecTableRow } from '@/components/spec-table';

const NONE: FeatureIconWithUrl[] = [];

/**
 * The price-tag icons each spec row's saved value carries (SPEC-VALUE-ICONS).
 *
 * The SAME list the print page and the designer read (`GET /dealer-kit/feature-icons`, shared
 * cache `FEATURE_ICONS_KEY` on `kitLibraryClient`, which a spec key save and a company switch
 * already refresh) and the same matcher (`iconsForSpecValue` over `featureIconsFor`), so the tab
 * cannot disagree with the tag. Owner 9 Nov: only `dealer_kit.tag_templates.view` holders see
 * icons (the endpoint's own gate, no RBAC change); the list is never fetched for anyone else.
 * `canManage` (`dealer_kit.library.manage`, the gate on setting icons) decides the click-through.
 */
export function useSpecValueIcons() {
  const { permissionSet, isLoading } = usePermissions();
  const canView = !isLoading && permissionSet.has('dealer_kit.tag_templates.view');
  const canManage = !isLoading && permissionSet.has('dealer_kit.library.manage');

  // A list that will not load leaves the table as it was; it must not break the tab.
  const { data } = useQuery(
    { queryKey: FEATURE_ICONS_KEY, queryFn: async () => listFeatureIcons(), enabled: canView },
    kitLibraryClient,
  );
  const icons = canView ? data : undefined;

  const iconsFor = useCallback(
    (row: SpecTableRow): FeatureIconWithUrl[] =>
      row.unknownKey ? NONE : iconsForSpecValue(row.specKey, row.value, icons),
    [icons],
  );

  return { iconsFor, canManage };
}
