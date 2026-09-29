'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getCostPriceVerificationSetting,
  updateCostPriceVerificationSetting,
} from '@/app/(protected)/procurement-management/cost-price-uploads/services/costPriceService';

const QUERY_KEY = ['cost-price-verification-setting'];

/**
 * `cost_price_verification_enabled` (#1288, plan section 4.6): off by default, one system
 * settings switch. Phase 1 mock: `costPriceService`'s module-level flag doubles as the
 * setting AND the toggle the change-set review page reads to show its verification-on
 * views - see that service file's own comment for why there is no separate mock constant.
 */
export function useCostPriceVerificationSetting() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: getCostPriceVerificationSetting,
  });
}

export function useUpdateCostPriceVerificationSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => updateCostPriceVerificationSetting(enabled),
    onSuccess: (result) => {
      queryClient.setQueryData(QUERY_KEY, result);
      toast.success(
        result.enabled
          ? 'Cost price uploads now need a second person to verify.'
          : 'Cost price uploads no longer need a second person to verify.',
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
