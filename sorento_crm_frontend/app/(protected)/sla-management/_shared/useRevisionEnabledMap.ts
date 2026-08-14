'use client';

import { useQuery } from '@tanstack/react-query';
import { getRevisionEnabledMap } from './formRevisionsService';

/**
 * Per-type revision enablement, cached across every form detail page.
 *
 * One tenant-wide setting, so the key carries no entity and the payload is
 * shared by the stock inquiry, purchase request and sponsorship form pages. The
 * stale window is generous on purpose: it changes only when an admin edits
 * Settings, and the cost of being a few minutes late is a tab that appears on
 * the next navigation.
 *
 * If the map comes back undefined and the Revisions tab never appears, the first
 * thing to check is NOT this hook: the endpoint lives on the backend's FORMS
 * router (`require_module_enabled_with_api_key("forms")`) while every consumer is
 * a PROCUREMENT page, so a tenant with forms disabled, strict module guarding and
 * a non-admin user 403s here and the tab silently disappears. Documented on the
 * endpoint itself (`app/api/v1/forms/revision_configs.py`); moving the route was
 * considered and declined.
 */
export function useRevisionEnabledMap() {
  return useQuery({
    queryKey: ['portal-revision-enabled-map'],
    queryFn: getRevisionEnabledMap,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
