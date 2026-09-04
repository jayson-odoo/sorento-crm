import { useMutation } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getContactPortalLink,
  sendContactPortalLink,
  type PortalLinkResponse,
  type PortalLinkSendResponse,
} from '@/services/contactPortalLinkService';

export function useContactPortalLinkMutation() {
  return useMutation<PortalLinkResponse, Error, string>({
    mutationFn: getContactPortalLink,
    onError: (err) => toast.error(err.message),
  });
}

export function useSendContactPortalLinkMutation() {
  return useMutation<PortalLinkSendResponse, Error, string>({
    mutationFn: sendContactPortalLink,
    onError: (err) => toast.error(err.message),
  });
}
