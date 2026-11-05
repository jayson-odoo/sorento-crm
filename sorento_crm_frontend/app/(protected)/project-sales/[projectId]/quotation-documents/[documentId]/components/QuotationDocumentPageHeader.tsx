'use client';

import * as React from 'react';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
import { Badge } from '@/components/ui/badge';
import { AUTOCOUNT_NOT_ACCEPTED_TEXT } from '@/lib/autocountWriteWording';
import { AutocountDecideMenu } from '../../../../_shared/components/AutocountDecideMenu';
import { AutocountWriteButton } from '../../../../_shared/components/AutocountWriteButton';
import { AutocountWriteDialog } from '../../../../_shared/components/AutocountWriteDialog';
import {
  useAutocountWriteAccess,
  useAutocountWriteCapabilities,
  useCancelQuotationInAutocount,
  useSendQuotationToAutocount,
} from '../../../../_shared/hooks/useProjectAutocountWrite';
import { useQuotationDocument } from '../../../../_shared/hooks/useQuotationDocuments';
import type { AutocountWriteResult } from '../../../../_shared/types/projectAutocountWrite.types';
import { documentNoun, type QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

/**
 * The page title is the document NUMBER, not the id in the URL (no UUIDs in the
 * UI), and the trail below it ends on that same number.
 *
 * The trail is passed rather than derived: the sidebar stops at Pipeline, so on
 * its own it would read "Dashboards > <number>" and offer no way back to the
 * project the document belongs to.
 *
 * It reads the same cached query the screen below it uses, so naming the page
 * costs no extra request; "Quotation Document" stands in only for the moment
 * before that query answers.
 *
 * Not to be confused with `QuotationDocumentHeader`, which is the letterhead
 * card inside the record.
 */
export function QuotationDocumentPageHeader({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  const document = useQuotationDocument(projectId, documentId);
  // PS-PROPOSAL-QUOTATION: the noun says which one this is, "Proposal PRJQ-..." / "Quotation QT-...".
  const title = document.data
    ? `${documentNoun(document.data)} ${document.data.document_no}`
    : 'Proposal';
  return (
    <PageHeader
      title={title}
      crumbs={projectCrumbs(projectId, { tab: 'quotations' }, { title })}
      actions={
        <>
          {/* AC-QTSO-CRM: mounted once the document has loaded; it renders nothing for a proposal. */}
          {document.data?.kind && (
            <QuotationAutocountActions documentId={documentId} doc={document.data} />
          )}
          <BackToList
            listPath={`/project-sales/${projectId}?tab=quotations`}
            label="Back to project"
            appendListState={false}
          />
        </>
      }
    />
  );
}

/**
 * Create / Update / Decide > Cancel in AutoCount. Off (switch or permission) renders nothing at
 * all, not a greyed ghost. Create before acceptance is greyed with the reason (R5).
 */
function QuotationAutocountActions({
  documentId,
  doc,
}: {
  documentId: string;
  doc: QuotationDocument;
}) {
  const writeAccess = useAutocountWriteAccess();
  const capabilities = useAutocountWriteCapabilities(writeAccess);
  const send = useSendQuotationToAutocount();
  const cancel = useCancelQuotationInAutocount();
  const [cancelResult, setCancelResult] = React.useState<AutocountWriteResult | null>(null);

  if (!writeAccess || doc.kind !== 'quotation') return null;

  const createCap = capabilities.data?.quotations?.create_doc;
  const editCap = capabilities.data?.quotations?.edit_doc;
  const cancelCap = capabilities.data?.quotations?.cancel_doc;
  const createReason = !doc.latest_issue_accepted
    ? AUTOCOUNT_NOT_ACCEPTED_TEXT
    : createCap && !createCap.enabled
      ? createCap.reason
      : null;
  const updateReason = editCap && !editCap.enabled ? editCap.reason : null;

  return (
    <>
      {doc.in_autocount && doc.autocount_doc_no && (
        <Badge variant="secondary" appearance="light" title="AutoCount number">
          {doc.autocount_doc_no}
        </Badge>
      )}
      {!doc.in_autocount && (
        <AutocountWriteButton
          label="Create in AutoCount"
          pendingLabel="Creating…"
          variant="primary"
          run={() => send.mutateAsync(documentId)}
          disabled={Boolean(createReason)}
          title={createReason ?? undefined}
        />
      )}
      {doc.in_autocount && doc.autocount_needs_update && (
        <AutocountWriteButton
          label="Update in AutoCount"
          pendingLabel="Updating…"
          variant="primary"
          run={() => send.mutateAsync(documentId)}
          disabled={Boolean(updateReason)}
          title={updateReason ?? undefined}
        />
      )}
      {doc.in_autocount && (
        <AutocountDecideMenu
          label="Decide"
          items={[
            {
              key: 'cancel',
              label: 'Cancel in AutoCount',
              enabled: Boolean(cancelCap?.enabled),
              reason: cancelCap ? cancelCap.reason : 'Checking AutoCount…',
              onSelect: () =>
                cancel
                  .mutateAsync(documentId)
                  .then(setCancelResult)
                  .catch(() => undefined),
            },
          ]}
        />
      )}
      <AutocountWriteDialog
        open={cancelResult !== null}
        onOpenChange={(open) => {
          if (!open) setCancelResult(null);
        }}
        title="Cancel in AutoCount"
        result={cancelResult}
      />
    </>
  );
}
