'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  acceptQuotation,
  getQuotationSignPage,
  QuotationSignError,
  requestQuotationChanges,
  submitAmendmentRequest,
  type QuotationSignAcceptBody,
  type QuotationSignAmendmentBody,
  type QuotationSignChangesBody,
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

  /**
   * The other decision, written into the cache the same way and for the same reason: the customer
   * has just told us the price is wrong, and the one thing they need back is confirmation that it
   * arrived. A refetch would answer that with a spinner.
   */
  const requestChanges = useMutation({
    mutationFn: (body: QuotationSignChangesBody) => requestQuotationChanges(token, body),
    onSuccess: (page: QuotationSignPage) => {
      queryClient.setQueryData(quotationSignPageKey(token), page);
      toast.success('Thank you. Your request has been sent to Sorento.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * The customer's suggested changes, answered with the page like the other two. A 409 means the
   * page moved on under a stale tab (a newer revision, or a request already open), so the page is
   * read again to show what it now is.
   */
  const submitAmendment = useMutation({
    mutationFn: (body: QuotationSignAmendmentBody) => submitAmendmentRequest(token, body),
    onSuccess: (page: QuotationSignPage) => {
      queryClient.setQueryData(quotationSignPageKey(token), page);
      toast.success('Thank you. Your suggestions have been sent to Sorento.');
    },
    onError: (error: Error) => {
      toast.error(error.message);
      if (error instanceof QuotationSignError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: quotationSignPageKey(token) });
      }
    },
  });

  return { accept, requestChanges, submitAmendment };
}
