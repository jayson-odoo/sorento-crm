'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { sanitizedHtml } from '@/lib/sanitize';

/**
 * The prose half of the quotation: the letter the customer reads before the prices, and the
 * clauses they hold us to afterwards.
 *
 * Both arrive as HTML, rendered from the company's active template with the names already
 * filled in. It goes through `sanitizedHtml` because the stored copy is editable, and an
 * editable HTML field is untrusted input no matter who last typed in it.
 *
 * A missing letter renders the panel with an empty state rather than dropping it: a section
 * that vanishes reads as "this quotation has no cover letter feature" instead of "nothing has
 * been written yet".
 */
function EmptyLine({ children }: { children: React.ReactNode }) {
  return <p className="min-w-0 break-words text-sm text-muted-foreground">{children}</p>;
}

export function QuotationCoverLetterPanel({ html }: { html: string | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">Cover letter</CardTitle>
      </CardHeader>
      <CardContent className="py-5">
        {html ? (
          <div
            className="prose prose-sm max-w-none break-words text-sm"
            dangerouslySetInnerHTML={sanitizedHtml(html)}
          />
        ) : (
          <EmptyLine>
            No cover letter on this quotation yet. It is filled in from the company template
            when the quotation is issued.
          </EmptyLine>
        )}
      </CardContent>
    </Card>
  );
}

export function QuotationTermsPanel({ html }: { html: string | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">Terms and conditions</CardTitle>
      </CardHeader>
      <CardContent className="py-5">
        {html ? (
          <div
            className="prose prose-sm max-w-none break-words text-sm"
            dangerouslySetInnerHTML={sanitizedHtml(html)}
          />
        ) : (
          <EmptyLine>
            No terms on this quotation yet. They are filled in from the company template when
            the quotation is issued.
          </EmptyLine>
        )}
      </CardContent>
    </Card>
  );
}
