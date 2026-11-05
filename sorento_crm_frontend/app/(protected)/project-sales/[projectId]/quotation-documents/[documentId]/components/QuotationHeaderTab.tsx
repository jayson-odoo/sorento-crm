'use client';

import * as React from 'react';
import { QuotationDocumentHeader, useQuotationHeaderDetails } from './QuotationDocumentHeader';
import { QuotationScopesTab } from './QuotationScopesTab';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';

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
