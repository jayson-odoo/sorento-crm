import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { toast } from '@/lib/toast';
import { apiFetch } from '@/lib/api';

export interface OrderStatusSelectOption {
  id: string;
  status_code: string;
  status_name: string;
}

export const useOrderStatusSelectQuery = () => {
  const { status: sessionStatus } = useSession();

  const fetchOrderStatusList = async (): Promise<OrderStatusSelectOption[]> => {
    try {
      const response = await apiFetch('/api/v1/order-management/order-statuses/select');

      if (!response.ok) {
        let errorBody: unknown;
        try {
          errorBody = await response.json();
        } catch {
          try {
            errorBody = await response.text();
          } catch {
            errorBody = '(could not read body)';
          }
        }
        console.error('[order-status-select] API error:', {
          status: response.status,
          statusText: response.statusText,
          url: response.url,
          detail: errorBody,
        });
        if (response.status !== 401) {
          toast.error(
            'Something went wrong while loading delivery order statuses. Please try again.',
            {
              position: 'top-center',
            },
          );
        }
        return [];
      }

      const json = await response.json();
      const raw = Array.isArray(json?.data) ? json.data : [];
      // Normalize: ensure status_code exists (API may send snake_case or camelCase)
      return raw.map((s: Record<string, unknown>) => ({
        id: String(s?.id ?? ''),
        status_code: String((s as { status_code?: string }).status_code ?? (s as { statusCode?: string }).statusCode ?? ''),
        status_name: String((s as { status_name?: string }).status_name ?? (s as { statusName?: string }).statusName ?? ''),
      }));
    } catch (err) {
      console.error('[order-status-select] Request failed:', err);
      toast.error(
        'Something went wrong while loading delivery order statuses. Please try again.',
        { position: 'top-center' },
      );
      return [];
    }
  };

  return useQuery({
    queryKey: ['order-status-select'],
    queryFn: fetchOrderStatusList,
    enabled: sessionStatus === 'authenticated',
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 2,
  });
};
