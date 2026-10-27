import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { createSetApart, getSetApartCustomers, updateSetApart } from '../services/setApartService';
import type { SetApartListParams, SetApartSavePayload } from '../types/setApart.types';

export const SET_APART_KEY = ['sales-set-apart'] as const;

export function useSetApartCustomers(params: SetApartListParams) {
  return useQuery({
    queryKey: [...SET_APART_KEY, params],
    queryFn: () => getSetApartCustomers(params),
    placeholderData: (previous) => previous,
  });
}

/** One save for the modal: a create when there is no id, else a PATCH. */
export function useSaveSetApart() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string | null; payload: SetApartSavePayload }) =>
      id ? updateSetApart(id, payload) : createSetApart(payload),
    onSuccess: (_row, { id }) => {
      queryClient.invalidateQueries({ queryKey: SET_APART_KEY });
      toast.success(id ? 'Set-apart customer saved' : 'Set-apart customer added');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save the customer'),
  });
}
