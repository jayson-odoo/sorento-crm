'use client';

import * as React from 'react';
import { documentNoun } from '../../../../_shared/services/quotationDocumentService';
import { QuotationCoverLetterPanel, QuotationTermsPanel } from './QuotationLetterPanels';
import { QuotationSignatureBlock } from './QuotationSignatureBlock';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';
import { useQuotationCoverPreview } from '../../../../_shared/hooks/useQuotationDocuments';

/**
 * The Header tab lives in `QuotationHeaderTab.tsx` (it carries the lines grid, and keeping it out
 * of this module keeps the prose tabs' routes off the DataGrid).
 *
 * The three prose tabs, each one nothing but the panel it always was plus the document the layout
 * already fetched.
 *
 * The panels themselves are untouched on purpose. What the client asked for was to stop scrolling
 * past fifty priced lines to reach the terms, not for the terms to read differently.
 */
export function QuotationCoverLetterTab() {
  const { projectId, document } = useQuotationDocumentScreen();
  // A read: the preview of the saved quotation; the intro and closing are edited with the rest
  // of the quotation in the form page (#1341).
  const preview = useQuotationCoverPreview(projectId, { document_id: document.id });
  return (
    <QuotationCoverLetterPanel
      cover={preview.data}
      isLoading={preview.isLoading}
      noun={documentNoun(document)}
      error={preview.error?.message}
    />
  );
}

export function QuotationTermsTab() {
  const { document } = useQuotationDocumentScreen();
  return (
    <QuotationTermsPanel
      html={document.terms_html}
      paymentTerms={document.payment_terms ?? null}
      validity={document.validity ?? null}
    />
  );
}

export function QuotationSignaturesTab() {
  const { document, latestIssue, sorentoSignature } = useQuotationDocumentScreen();
  return (
    /* The counter-signature is read off the LATEST issue, which is the copy the customer is
       holding. An older revision may have been accepted too, but what this panel answers is
       "where does the current quotation stand", and that is the newest one. */
    <QuotationSignatureBlock
      document={document}
      sorentoSignature={sorentoSignature}
      customerSignature={latestIssue?.customer_signature ?? null}
      acceptedAt={latestIssue?.accepted_at ?? null}
      changesRequestedAt={latestIssue?.changes_requested_at ?? null}
      changesRequestedNote={latestIssue?.changes_requested_note ?? null}
      changesRequestedByName={latestIssue?.changes_requested_by_name ?? null}
    />
  );
}
