import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getRespondContactsOutbound,
  setBulkOutbound,
  setContactOutbound,
} from '../services/respondContactOutboundService';
import type { OutboundFilter } from '../types/respondContactOutbound.types';

export const RESPOND_CONTACTS_OUTBOUND_KEY = 'respond-contacts-outbound';

export function useRespondContactsOutbound(
  params: DataGridApiFetchParams & { outbound?: OutboundFilter },
) {
  return useQuery({
    queryKey: [
      RESPOND_CONTACTS_OUTBOUND_KEY,
      params.pageIndex,
      params.pageSize,
      params.searchQuery,
      params.outbound,
    ],
    queryFn: () => getRespondContactsOutbound(params),
    staleTime: 1000 * 15,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useRespondContactOutboundMutations() {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: [RESPOND_CONTACTS_OUTBOUND_KEY] });

  const setOne = useMutation({
    mutationFn: ({ contactId, enabled }: { contactId: string; enabled: boolean }) =>
      setContactOutbound(contactId, enabled),
    onSuccess: (row) => {
      void invalidate();
      const who = row.name || row.phone_number || 'Contact';
      toast.success(
        row.outbound_enabled
          ? `${who} can be messaged again.`
          : `${who} will receive no WhatsApp messages.`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const setBulk = useMutation({
    mutationFn: (payload: { enabled: boolean; contactIds?: string[]; all?: boolean }) =>
      setBulkOutbound(payload),
    onSuccess: (result, variables) => {
      void invalidate();
      if (result.changed === 0) {
        toast.info('Nothing to change - those contacts were already set that way.');
        return;
      }
      toast.success(
        variables.enabled
          ? `Outbound messaging enabled for ${result.changed} contact(s).`
          : `Outbound messaging disabled for ${result.changed} contact(s).`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { setOne, setBulk };
}
