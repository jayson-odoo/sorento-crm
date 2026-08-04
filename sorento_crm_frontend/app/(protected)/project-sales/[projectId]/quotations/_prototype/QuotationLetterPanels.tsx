'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { MockDocument } from './documentMocks';

/**
 * The prose half of the quotation: the letter the customer reads before the prices, and
 * the clauses they hold us to afterwards.
 *
 * Both arrive already written, rendered from the company's active template with the
 * names filled in (AC-E2). What the salesperson edits here is THIS document's copy - the
 * template is a separate object and stays untouched, which is the one thing a reader
 * cannot infer from the screen and so is the one thing the screen says out loud.
 */
export function QuotationCoverLetterPanel({
  letter,
  canEdit,
  onEdit,
}: {
  letter: MockDocument['cover_letter'];
  canEdit: boolean;
  onEdit?: () => void;
}) {
  // The stored letter keeps its paragraph breaks as blank lines. Rendering the raw string
  // would collapse them into one wall of text, which is not what was written.
  const paragraphs = letter.split('\n\n').filter((part) => part.trim().length > 0);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words text-sm">Cover letter</CardTitle>
        {canEdit && onEdit && (
          <Button variant="outline" size="sm" onClick={onEdit}>
            Edit for this quotation
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4 py-5">
        <p className="text-xs text-muted-foreground">
          Rendered from the company template. Editing it here changes this quotation only,
          never the template.
        </p>

        {paragraphs.length > 0 ? (
          <div className="space-y-3">
            {paragraphs.map((paragraph, index) => (
              <p key={index} className="min-w-0 break-words text-sm leading-relaxed">
                {paragraph}
              </p>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">-</p>
        )}
      </CardContent>
    </Card>
  );
}

export function QuotationTermsPanel({ terms }: { terms: MockDocument['terms'] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">Terms and conditions</CardTitle>
      </CardHeader>
      <CardContent className="py-5">
        {terms.length > 0 ? (
          <ol className="list-decimal space-y-2 ps-5">
            {terms.map((clause, index) => (
              <li key={index} className="min-w-0 break-words text-sm leading-relaxed">
                {clause}
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">-</p>
        )}
      </CardContent>
    </Card>
  );
}
