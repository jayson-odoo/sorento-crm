import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  checkCertificateLinks,
  confirmCertificateLinks,
  getCertificateLinks,
  type CertificateLinksParams,
} from '../services/certificateLinkService';

/** CERT-LINK-CLEANUP hooks. Layering: components -> THESE hooks -> services/certificateLinkService. */
export const CERTIFICATE_LINKS_KEY = 'certificate-links';

export function useCertificateLinks(params: CertificateLinksParams, options?: { refetchInterval?: number | false }) {
  return useQuery({
    queryKey: [
      CERTIFICATE_LINKS_KEY,
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.certificateId,
      params.verdicts,
      params.source,
    ],
    queryFn: () => getCertificateLinks(params),
    ...LIST_QUERY_OPTIONS,
    refetchInterval: options?.refetchInterval,
  });
}

export function useCheckCertificateLinks() {
  return useMutation({ mutationFn: checkCertificateLinks });
}

export function useConfirmCertificateLinks() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => confirmCertificateLinks(ids),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: [CERTIFICATE_LINKS_KEY] });
      void queryClient.invalidateQueries({ queryKey: ['certificates'] });
      toast.success(`${result.confirmed} link${result.confirmed === 1 ? '' : 's'} confirmed`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
