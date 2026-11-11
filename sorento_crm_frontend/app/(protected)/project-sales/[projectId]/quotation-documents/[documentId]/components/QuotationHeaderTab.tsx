'use client';

import * as React from 'react';
import { FormSection } from '@/components/common/FormSection';
import {
  QuotationDocumentHeader,
  headerSummary,
  linesSummary,
  useQuotationHeaderDetails,
} from './QuotationDocumentHeader';
import { QuotationScopesTab } from './QuotationScopesTab';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';

/**
 * The Header tab, first of the tabs (#1341): the letterhead card the customer reads (To, Attn,
 * Project, Our Ref, Your Ref, Date, who issued and opened it, Total), then the lines under it
 * (PROPOSAL-HEADER-LAYOUT, owner 5 Nov 2026: "for quotation I think the lines better be same page
 * with Header for easy view"; the Lines tab is gone).
 *
 * Both fold, as on the form page (QUOTE-HEADER-TIDY, owner 11 Nov 2026: "even in view the header
 * and line should be collapsible"): the same `FormSection`, open on arrival, no persistence, the
 * same one-line summaries.
 */
export function QuotationHeaderTab() {
  const { projectId, document } = useQuotationDocumentScreen();
  const details = useQuotationHeaderDetails(projectId, document.scopes ?? []);
  const [headerOpen, setHeaderOpen] = React.useState(true);
  const [linesOpen, setLinesOpen] = React.useState(true);
  return (
    <div className="space-y-5">
      <FormSection
        title="Header"
        summary={headerSummary(document, document.grand_total)}
        open={headerOpen}
        onOpenChange={setHeaderOpen}
        // The letterhead is its own card, so the section drops its padding and that card's frame.
        bodyClassName="p-0 *:rounded-none *:border-0 *:shadow-none"
      >
        <QuotationDocumentHeader document={document} details={details} />
      </FormSection>
      <FormSection
        title="Lines"
        summary={linesSummary((document.scopes ?? []).length, document.grand_total)}
        open={linesOpen}
        onOpenChange={setLinesOpen}
        // The lines' own card (or the empty state's) sits inside this one: drop its frame so the
        // fold reads as one card, as on the form page.
        bodyClassName="[&>[data-slot=card]]:border-0 [&>[data-slot=card]]:shadow-none [&>*>[data-slot=card]]:border-0 [&>*>[data-slot=card]]:shadow-none [&>*>[data-slot=card]>[data-slot=card-content]]:px-0"
      >
        <QuotationScopesTab />
      </FormSection>
    </div>
  );
}
