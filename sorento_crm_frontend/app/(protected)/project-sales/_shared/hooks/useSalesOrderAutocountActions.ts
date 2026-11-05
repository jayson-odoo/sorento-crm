'use client';

import * as React from 'react';
import {
  cancelInAutocountState,
  createInAutocountState,
  updateInAutocountState,
} from '../lib/autocountWriteRules';
import type { ProjectSalesOrderRow } from '../types/projectSalesOrder.types';
import type { AutocountWriteResult } from '../types/projectAutocountWrite.types';
import {
  useAutocountWriteAccess,
  useAutocountWriteCapabilities,
  useCancelSalesOrderInAutocount,
  useCreateSalesOrderInAutocount,
} from './useProjectAutocountWrite';

/**
 * The AutoCount actions of ONE sales order (its detail page; the worksheet reads the same rules).
 * Nothing renders when the switch is off or the permission is missing (`access`). The result
 * dialog is the caller's, rendered OUTSIDE any menu: a menu unmounts its items when one is
 * picked, and the answer must outlive that.
 */
export function useSalesOrderAutocountActions(
  order:
    | Pick<
        ProjectSalesOrderRow,
        'id' | 'status' | 'autocount_doc_no' | 'in_autocount' | 'autocount_cancelled'
      > & { can_export?: boolean }
    | undefined,
) {
  const access = useAutocountWriteAccess();
  const capabilities = useAutocountWriteCapabilities(access);
  const create = useCreateSalesOrderInAutocount();
  const cancel = useCancelSalesOrderInAutocount();
  const [result, setResult] = React.useState<AutocountWriteResult | null>(null);

  const caps = capabilities.data;
  const capsLoading = capabilities.isLoading;
  const createState = order
    ? createInAutocountState({
        status: order.status,
        canExport: Boolean(order.can_export),
        autocountDocNo: order.autocount_doc_no,
        inAutocount: order.in_autocount,
        caps,
        capsLoading,
      })
    : null;
  const cancelState = order
    ? cancelInAutocountState({
        inAutocount: Boolean(order.in_autocount),
        cancelled: Boolean(order.autocount_cancelled),
        caps,
        capsLoading,
      })
    : null;
  const updateState = updateInAutocountState({ caps, capsLoading });

  const run = (mutate: (id: string) => Promise<AutocountWriteResult>) => {
    if (!order) return;
    mutate(order.id)
      .then(setResult)
      .catch(() => undefined); // toasted by the mutation
  };

  return {
    access,
    createState,
    cancelState,
    updateState,
    runCreate: () => run(create.mutateAsync),
    runCancel: () => run(cancel.mutateAsync),
    pending: create.isPending || cancel.isPending,
    result,
    clearResult: () => setResult(null),
  };
}
