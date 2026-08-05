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
  const { document, canEdit, edit } = useQuotationDocumentScreen();
  const staged = edit.documentDraft.cover_letter_html;
  const editing = canEdit && edit.isEditing;
  return (
    <QuotationCoverLetterPanel
      // The staged copy while one exists, so leaving for the scopes tab and coming back shows
      // what was typed rather than what the server still holds.
      html={staged !== undefined ? staged : document.cover_letter_html}
      onChange={
        editing ? (html) => edit.stageDocument({ cover_letter_html: html }) : undefined
      }
    />
  );
}

export function QuotationTermsTab() {
  const { document, canEdit, edit } = useQuotationDocumentScreen();
  const staged = edit.documentDraft.terms_html;
  const editing = canEdit && edit.isEditing;
  return (
    <QuotationTermsPanel
      html={staged !== undefined ? staged : document.terms_html}
      onChange={editing ? (html) => edit.stageDocument({ terms_html: html }) : undefined}
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
    />
  );
}
