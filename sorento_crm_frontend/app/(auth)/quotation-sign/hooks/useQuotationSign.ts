'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  acceptQuotation,
  getQuotationSignPage,
  QuotationSignError,
  type QuotationSignAcceptBody,
  type QuotationSignPage,
} from '../services/quotationSignService';

const PAGE_KEY = 'quotation-sign-page';

export const quotationSignPageKey = (token: string) => [PAGE_KEY, token];

export function useQuotationSignPage(token: string) {
  return useQuery({
    queryKey: quotationSignPageKey(token),
    queryFn: () => getQuotationSignPage(token),
    enabled: Boolean(token),
    /**
     * A dead link is a final answer, not a blip: retrying it three times makes the customer
     * stare at a spinner before reading the one sentence that helps them. Anything else (a
     * flaky connection on a phone) is still worth one retry.
     */
    retry: (attempt, error) =>
      error instanceof QuotationSignError && error.isDeadLink ? false : attempt < 1,
  });
}

export function useQuotationSignMutations(token: string) {
  const queryClient = useQueryClient();

  /**
   * The accept response IS the page, so it is written straight into the cache rather than
   * invalidated: the screen must flip to Accepted with the signature the customer just applied,
   * and a refetch would show them a spinner in the one moment they need confirmation.
   */
  const accept = useMutation({
    mutationFn: (body: QuotationSignAcceptBody) => acceptQuotation(token, body),
    onSuccess: (page: QuotationSignPage) => {
      queryClient.setQueryData(quotationSignPageKey(token), page);
      toast.success('Thank you. Your acceptance has been recorded.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { accept };
}
