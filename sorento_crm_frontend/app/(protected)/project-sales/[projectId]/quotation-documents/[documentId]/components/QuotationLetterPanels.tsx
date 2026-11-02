'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { sanitizedHtml } from '@/lib/sanitize';
import { TERMS_HTML_CLASS } from '@/lib/terms-html';

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
 *
 * `onChange` is what makes a panel editable, and it is only handed down while the document's
 * edit session is open. Typing here changes nothing on the server: it stages, and the screen's
 * one Save sends it with the lines.
 */
function EmptyLine({ children }: { children: React.ReactNode }) {
  return <p className="min-w-0 break-words text-sm text-muted-foreground">{children}</p>;
}

function LetterPanel({
  title,
  html,
  emptyHint,
  placeholder,
  readClass = 'prose prose-sm max-w-none break-words text-sm',
  onChange,
}: {
  title: string;
  html: string | null;
  emptyHint: React.ReactNode;
  placeholder: string;
  /** Class of the read-mode HTML block. */
  readClass?: string;
  /** Set only in an edit session. Absent means this is a read. */
  onChange?: (html: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="min-w-0 py-5">
        {onChange ? (
          // The repo's one rich-text surface, so this reads and behaves like every other
          // long-form field in the system rather than being a second editor to learn.
          <RichTextEditor value={html ?? ''} onChange={onChange} placeholder={placeholder} />
        ) : html ? (
          <div
            className={readClass}
            dangerouslySetInnerHTML={sanitizedHtml(html)}
          />
        ) : (
          <EmptyLine>{emptyHint}</EmptyLine>
        )}
      </CardContent>
    </Card>
  );
}

export function QuotationCoverLetterPanel({
  html,
  onChange,
}: {
  html: string | null;
  onChange?: (html: string) => void;
}) {
  return (
    <LetterPanel
      title="Cover letter"
      html={html}
      onChange={onChange}
      placeholder="The letter the customer reads before the prices"
      emptyHint="No cover letter on this quotation yet."
    />
  );
}

export function QuotationTermsPanel({
  html,
  onChange,
  paymentTerms = null,
  validity = null,
  onFieldChange,
}: {
  html: string | null;
  onChange?: (html: string) => void;
  paymentTerms?: string | null;
  validity?: string | null;
  /** Set only in an edit session, with `onChange`. */
  onFieldChange?: (patch: { payment_terms?: string | null; validity?: string | null }) => void;
}) {
  const fields = [
    { id: 'quotation-payment-terms', label: 'Payment Terms', key: 'payment_terms', value: paymentTerms },
    { id: 'quotation-validity', label: 'Validity', key: 'validity', value: validity },
  ] as const;
  const shown = onFieldChange ? fields : fields.filter((field) => (field.value ?? '').trim());
  return (
    <div className="space-y-4">
      {shown.length > 0 && (
        <Card>
          <CardContent className="grid gap-4 py-5 sm:grid-cols-2">
            {shown.map((field) =>
              onFieldChange ? (
                <div key={field.key} className="min-w-0 space-y-1.5">
                  <Label htmlFor={field.id}>{field.label}</Label>
                  <Input
                    id={field.id}
                    value={field.value ?? ''}
                    onChange={(event) => onFieldChange({ [field.key]: event.target.value || null })}
                  />
                </div>
              ) : (
                <div key={field.key} className="min-w-0 space-y-1">
                  <p className="text-sm text-muted-foreground">{field.label}</p>
                  <p className="min-w-0 break-words text-sm font-medium">{field.value}</p>
                </div>
              ),
            )}
          </CardContent>
        </Card>
      )}
      <LetterPanel
        title="Terms and conditions"
        html={html}
        onChange={onChange}
        readClass={TERMS_HTML_CLASS}
        placeholder="The clauses the customer holds us to"
        emptyHint="No terms on this quotation yet."
      />
    </div>
  );
}
