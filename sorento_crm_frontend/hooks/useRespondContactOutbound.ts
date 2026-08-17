'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  setBulkOutbound,
  setContactOutbound,
} from '@/app/(protected)/system-management/respond-contacts/services/respondContactOutboundService';

export const RESPOND_CONTACTS_OUTBOUND_KEY = 'respond-contacts-outbound';

/**
 * Every list that renders `respond_contacts.outbound_enabled`.
 *
 * The switch is per CONTACT but is shown on several grids, and on one of them
 * (contact x agent grants) the same contact owns several ROWS. So a write here
 * refreshes all of them - otherwise flipping a contact on one screen leaves a
 * stale badge on the next, and a second grant row for the same person keeps
 * showing the old state.
 */
const OUTBOUND_LIST_KEYS = [
  RESPOND_CONTACTS_OUTBOUND_KEY, // System Management -> Respond.io Contacts
  'respond-contacts', // Internal Users / Contacts grid
  'contact-access-agents', // Contact x agent grants (flat and grouped)
];

/**
 * The one door for writing the outbound kill switch from the UI.
 *
 * Shared on purpose: the Respond.io Contacts screen, the contacts grid and the
 * Contact Access Agents grid all flip the same column, so they must produce the
 * same request, the same toast and the same invalidations.
 */
export function useRespondContactOutboundMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    for (const key of OUTBOUND_LIST_KEYS) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };

  const setOne = useMutation({
    mutationFn: ({ contactId, enabled }: { contactId: string; enabled: boolean }) =>
      setContactOutbound(contactId, enabled),
    onSuccess: (row) => {
      invalidate();
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
      invalidate();
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
