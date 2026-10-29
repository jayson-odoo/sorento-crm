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
 */

import { useMemo, type ReactNode } from 'react';
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

/** The portal component under it talks to My Requests, on the CRM's paths, with D7 deletes. */
export function MyRequestClientProvider({ children }: { children: ReactNode }) {
  // One client per form: its lookup sets are cached per client, never shared with the portal's.
  const client = useMemo<SubmissionClient>(
    () => ({
      ...createMyRequestsSubmissionApi(),
      paths: myRequestsPaths,
      deletes: { DraftDelete, AttachmentRemove },
      embedded: true,
    }),
    [],
  );
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
  return (
    <MyRequestClientProvider>
      <SubmissionForm
        kind={kind}
        submissionId={submissionId}
        initialValues={submissionId ? undefined : initialValues}
      />
    </MyRequestClientProvider>
  );
}
