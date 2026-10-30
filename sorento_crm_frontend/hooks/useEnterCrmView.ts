'use client';

import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useImpersonation } from '@/hooks/useImpersonation';

/**
 * Switch the CRM to the view of a salesperson user (the existing CRM impersonation), then make
 * sure no cached admin profile or permissions survive into that view. Callers write the portal
 * token and navigate.
 */
export function useEnterCrmView() {
  const { start } = useImpersonation();
  const queryClient = useQueryClient();
  return useCallback(
    async (crmUserId: string) => {
      await start(crmUserId);
      await queryClient.invalidateQueries();
    },
    [start, queryClient],
  );
}
