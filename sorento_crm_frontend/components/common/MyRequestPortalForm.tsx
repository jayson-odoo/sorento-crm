'use client';

/**
 * A salesperson's own request on a CRM page (PORTAL-P4-REQUESTS R1, form parity, owner rule):
 * the PORTAL's own SubmissionForm, create / edit / view alike, wired to `/api/v1/my-requests` by
 * the injected client. Same component, so the same fields, lookups, defaults and payload as the
 * portal. Two things differ by design: the page's header carries Back (`embedded`), and the two
 * deletes are parked on the server (D7) instead of confirmed - "Delete draft" parks
 * `my_request.delete`, removing an own upload parks `my_request_attachment.unlink`.
 *
 * `MyRequestClientProvider` is that client on its own, for the kinds with portal pages of their
 * own (Sample Request, New Product Application, Sales Opportunity, Price Tag Request; R3): the CRM
 * page wraps the portal's component in it.
 *
 * A saved complaint gets one tab the portal does not have (L3, owner a25895124 Q2 a): its
 * fulfilment DOs, read-only, after Details / Comments / Revisions (`extraTabs`).
 */

import { useMemo, type ReactNode } from 'react';
import ComplaintFulfilmentOrdersSection from '@/app/(protected)/complaint-management/complaints/components/ComplaintFulfilmentOrdersSection';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { MY_REQUEST_KEY } from '@/hooks/useMyRequests';
import { SubmissionForm, type SubmissionInitialValues } from '@/app/(auth)/portal/components/SubmissionForm';
import {
  SubmissionClientProvider,
  type AttachmentRemoveProps,
  type DraftDeleteProps,
  type SubmissionClient,
  type SubmissionExtraTab,
} from '@/app/(auth)/portal/lib/submission-client';
import { createMyRequestsSubmissionApi, myRequestsPaths } from '@/services/myRequestsSubmissionClient';
import type { MyRequestKind } from '@/services/myRequestsService';

/** The staff list each form's rows show on, refetched once a row or a file is gone. */
const LIST_KEYS: Record<string, string> = {
  stock_inquiry: 'stock-inquiries',
  complaint: 'complaints',
  purchase_request: 'purchase-requests',
  sponsorship_form: 'purchase-requests',
  sample_request: 'sample-requests',
  new_product_application: 'new-product-applications',
  sales_opportunity: 'sales-opportunities',
  price_tag_request: 'price-tag-requests',
};

function DraftDelete({ kind, submissionId, disabled, onDeleted }: DraftDeleteProps) {
  const remove = useDeferredAction({
    actionKey: 'my_request.delete',
    entityType: kind,
    entityId: submissionId,
    verb: 'Deleting',
    subject: '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Draft deleted',
    invalidateKeys: [[MY_REQUEST_KEY, kind], [LIST_KEYS[kind] ?? MY_REQUEST_KEY]],
    onCommitted: onDeleted,
  });
  return (
    <DeferredActionButton
      pending={remove.pending}
      verb="Deleting"
      onCancel={remove.cancel}
      idle={
        <Button
          type="button"
          variant="outline"
          className="text-destructive border-destructive/50 hover:bg-destructive/10"
          onClick={() => remove.start()}
          disabled={disabled || remove.isPending || remove.isBlocked}
        >
          <Trash2 className="size-4 mr-1" />
          Delete draft
        </Button>
      }
    />
  );
}

function AttachmentRemove({ kind, attachment, disabled, onRemoved }: AttachmentRemoveProps) {
  const remove = useDeferredAction({
    actionKey: 'my_request_attachment.unlink',
    entityType: 'my_request_attachment',
    entityId: attachment.link_id,
    verb: 'Removing',
    subject: '',
    surface: 'inline',
    // A handful per request: each reads `current` from mount, so a countdown started before a
    // reload (or in another tab) still shows on its row.
    watchFromMount: true,
    successMessage: 'File removed',
    invalidateKeys: [[MY_REQUEST_KEY, kind]],
    onCommitted: onRemoved,
  });
  return (
    <DeferredActionButton
      pending={remove.pending}
      verb="Removing"
      onCancel={remove.cancel}
      className="min-w-0"
      idle={
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => remove.start()}
          disabled={disabled || remove.isPending || remove.isBlocked}
          aria-label="Remove attachment"
        >
          <X className="h-4 w-4" />
        </Button>
      }
    />
  );
}

/** The calls of a kind's own service that change a row. */
const SERVICE_WRITE =
  /^(create|update|submit|cancel|revise|collect|delete|approve|requestChanges|requestPriceTagExport)/;

/** `fn`, then (once it resolved) the kind's staff list refetch. A throw skips it. */
function refreshing<A extends unknown[], R>(
  qc: QueryClient,
  keyOf: (...args: never[]) => string | undefined,
  fn: (...args: A) => Promise<R>,
): (...args: A) => Promise<R> {
  return async (...args: A) => {
    const result = await fn(...args);
    const list = (keyOf as (...a: unknown[]) => string | undefined)(...args);
    if (list) void qc.invalidateQueries({ queryKey: [list] });
    return result;
  };
}

/** A service with every write wrapped to refresh `list`. */
function refreshingService<T extends object>(qc: QueryClient, list: string, service: T): T {
  const out: Record<string, unknown> = { ...(service as Record<string, unknown>) };
  for (const [name, fn] of Object.entries(service)) {
    if (typeof fn === 'function' && SERVICE_WRITE.test(name)) {
      out[name] = refreshing(qc, () => list, fn as (...a: unknown[]) => Promise<unknown>);
    }
  }
  return out as T;
}

/** The portal component under it talks to My Requests, on the CRM's paths, with D7 deletes. Its
 *  writes refresh the CRM list of their kind (those lists never go stale on their own).
 *  `extraTabs`: the form's tabs beyond its own; pass a memoised array (it rebuilds the client). */
export function MyRequestClientProvider({
  children,
  extraTabs,
}: {
  children: ReactNode;
  extraTabs?: SubmissionExtraTab[];
}) {
  const qc = useQueryClient();
  // One client per form: its lookup sets are cached per client, never shared with the portal's.
  const client = useMemo<SubmissionClient>(() => {
    const api = createMyRequestsSubmissionApi();
    const listOf = (kind: unknown) => LIST_KEYS[String(kind)];
    return {
      ...api,
      saveDraft: refreshing(qc, listOf, api.saveDraft),
      submitDraft: refreshing(qc, listOf, api.submitDraft),
      deleteDraftSubmission: refreshing(qc, listOf, api.deleteDraftSubmission),
      saveRevisionDraft: refreshing(qc, listOf, api.saveRevisionDraft),
      discardRevisionDraft: refreshing(qc, listOf, api.discardRevisionDraft),
      reviseSubmission: refreshing(qc, listOf, api.reviseSubmission),
      uploadAttachment: refreshing(qc, listOf, api.uploadAttachment),
      sampleRequest: api.sampleRequest && refreshingService(qc, 'sample-requests', api.sampleRequest),
      newProductApplication:
        api.newProductApplication &&
        refreshingService(qc, 'new-product-applications', api.newProductApplication),
      salesOpportunity:
        api.salesOpportunity && refreshingService(qc, 'sales-opportunities', api.salesOpportunity),
      priceTagRequest:
        api.priceTagRequest && refreshingService(qc, 'price-tag-requests', api.priceTagRequest),
      paths: myRequestsPaths,
      deletes: { DraftDelete, AttachmentRemove },
      embedded: true,
      ...(extraTabs ? { extraTabs } : {}),
    };
  }, [qc, extraTabs]);
  return <SubmissionClientProvider client={client}>{children}</SubmissionClientProvider>;
}

export default function MyRequestPortalForm({
  kind,
  submissionId,
  initialValues,
}: {
  kind: MyRequestKind;
  /** None: a new request (`?from=<id>` duplicates one of theirs, as on the portal). */
  submissionId?: string;
  /** A new request's starting values (a project's stage action seeds its project). */
  initialValues?: SubmissionInitialValues;
}) {
  const extraTabs = useMemo<SubmissionExtraTab[] | undefined>(
    () =>
      kind === 'complaint' && submissionId
        ? [
            {
              value: 'fulfilment-dos',
              label: 'Fulfilment DOs',
              content: <ComplaintFulfilmentOrdersSection complaintId={submissionId} readOnly />,
            },
          ]
        : undefined,
    [kind, submissionId],
  );
  return (
    <MyRequestClientProvider extraTabs={extraTabs}>
      <SubmissionForm
        kind={kind}
        submissionId={submissionId}
        initialValues={submissionId ? undefined : initialValues}
      />
    </MyRequestClientProvider>
  );
}
