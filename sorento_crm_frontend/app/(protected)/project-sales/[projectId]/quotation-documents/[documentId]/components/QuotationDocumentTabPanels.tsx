'use client';

import * as React from 'react';
import { QuotationCoverLetterPanel, QuotationTermsPanel } from './QuotationLetterPanels';
import { QuotationSignatureBlock } from './QuotationSignatureBlock';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';

/**
 * The three prose tabs, each one nothing but the panel it always was plus the document the layout
 * already fetched.
 *
 * The panels themselves are untouched on purpose. What the client asked for was to stop scrolling
 * past fifty priced lines to reach the terms, not for the terms to read differently.
 */
export function QuotationCoverLetterTab() {
  const { document } = useQuotationDocumentScreen();
  return <QuotationCoverLetterPanel html={document.cover_letter_html} />;
}

export function QuotationTermsTab() {
  const { document } = useQuotationDocumentScreen();
  return <QuotationTermsPanel html={document.terms_html} />;
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
    />
  );
}
