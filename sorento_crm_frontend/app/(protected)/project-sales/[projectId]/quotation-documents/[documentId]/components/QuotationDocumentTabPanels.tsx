'use client';

import * as React from 'react';
import { documentNoun } from '../../../../_shared/services/quotationDocumentService';
import { QuotationCoverLetterPanel, QuotationTermsPanel } from './QuotationLetterPanels';
import { QuotationDocumentHeader, useQuotationHeaderDetails } from './QuotationDocumentHeader';
import { QuotationSignatureBlock } from './QuotationSignatureBlock';
import { QuotationScopesTab } from './QuotationScopesTab';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';
import { useQuotationCoverPreview } from '../../../../_shared/hooks/useQuotationDocuments';

/**
 * The three prose tabs, each one nothing but the panel it always was plus the document the layout
 * already fetched.
 *
 * The panels themselves are untouched on purpose. What the client asked for was to stop scrolling
 * past fifty priced lines to reach the terms, not for the terms to read differently.
 */
/**
 * The Header tab, first of the tabs (#1341): the letterhead card the customer reads (To, Attn,
 * Our Ref, Your Ref, Date, Total) and who issued and opened each scope's current version, then
 * the lines under it (PROPOSAL-HEADER-LAYOUT, owner 5 Nov 2026: "for quotation I think the lines
 * better be same page with Header for easy view"; the Lines tab is gone).
 */
export function QuotationHeaderTab() {
  const { projectId, document } = useQuotationDocumentScreen();
  const details = useQuotationHeaderDetails(projectId, document.scopes ?? []);
  return (
    <div className="space-y-5">
      <QuotationDocumentHeader document={document} details={details} />
      <QuotationScopesTab />
    </div>
  );
}

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
