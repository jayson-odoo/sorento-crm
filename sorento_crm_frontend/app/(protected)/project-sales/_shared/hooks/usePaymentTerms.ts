'use client';

import { useQuery } from '@tanstack/react-query';
import {
  listQuotationPaymentTerms,
  listTemplatePaymentTerms,
} from '../services/paymentTermService';

/** The Payment Terms select's options: the project's company's when `projectId` is given (the
 *  quotation form), else the acting company's (the terms template dialog). */
export function usePaymentTermOptions(projectId?: string) {
  return useQuery({
    queryKey: ['payment-term-options', projectId ?? 'config'],
    queryFn: () =>
      projectId ? listQuotationPaymentTerms(projectId) : listTemplatePaymentTerms(),
    staleTime: 5 * 60_000,
  });
}
