'use client';

import * as React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { sanitizedHtml } from '@/lib/sanitize';
import { TERMS_HTML_CLASS } from '@/lib/terms-html';
import type { CoverPageData } from '@/lib/quotation-cover';

function text(value: string | null | undefined): string {
  return value?.trim() ? value : '-';
}

/** The sender block: logo and company name. */
export function SenderRow({
  name,
  logoUrl,
  noun = 'Quotation',
}: {
  name: string | null | undefined;
  logoUrl: string | null | undefined;
  /** "Quotation" or "Proposal": the word the document prints for itself. */
  noun?: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      {logoUrl && (
        <img
          src={logoUrl}
          alt={`${name ?? 'Company'} logo`}
          referrerPolicy="no-referrer"
          className="h-12 w-auto max-w-[120px] shrink-0 object-contain"
        />
      )}
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {`${noun} from`}
        </p>
        <p className="min-w-0 break-words text-base font-semibold">
          {text(name)}
        </p>
      </div>
    </div>
  );
}

/**
 * The cover page: letterhead, title, intro, the label/value rows and closing, in the order the
 * PDF's first page prints them. The one component behind the customer sign link, the quotation's
 * Cover letter tab and the designer preview. A payload with no `cover_title` is the fixed #2088
 * cover (letterhead and rows only).
 *
 * `wide` keeps the label beside its value whatever the viewport is, for the A4 preview frame
 * whose natural width is a page, not a phone.
 */
export function CoverPageCard({
  cover,
  testId = 'cover-page-card',
  wide = false,
  noun = 'Quotation',
}: {
  cover: CoverPageData;
  testId?: string;
  wide?: boolean;
  noun?: string;
}) {
  const designed =
    cover.cover_title !== undefined && cover.cover_title !== null;
  const letterhead = designed ? cover.cover_show_letterhead !== false : true;
  const title = designed ? cover.cover_title?.trim() : '';
  const intro = cover.cover_intro_html?.trim();
  const closing = cover.cover_closing_html?.trim();
  return (
    <Card data-testid={testId}>
      <CardContent className="space-y-4 py-5">
        {letterhead && (
          <SenderRow name={cover.sender_name} logoUrl={cover.sender_logo_url} noun={noun} />
        )}
        {title && (
          <p className="min-w-0 break-words text-lg font-semibold tracking-wide">
            {title}
          </p>
        )}
        {intro && (
          <div
            className={cn(
              TERMS_HTML_CLASS,
              letterhead && 'border-t border-border pt-4',
            )}
            dangerouslySetInnerHTML={sanitizedHtml(intro)}
          />
        )}
        <div
          className={cn(
            'space-y-3',
            (letterhead || title || intro) && 'border-t border-border pt-4',
          )}
        >
          {cover.cover_rows.map((row) => (
            <div
              key={row.key}
              className={cn(
                'flex min-w-0 text-sm',
                wide ? 'flex-row gap-2' : 'flex-col gap-1 sm:flex-row sm:gap-2',
              )}
            >
              <span
                className={cn(
                  'shrink-0 text-muted-foreground',
                  wide ? 'w-40' : 'sm:w-40',
                )}
              >
                {row.label}
              </span>
              {row.html ? (
                <div
                  className={cn(TERMS_HTML_CLASS, 'font-medium')}
                  dangerouslySetInnerHTML={sanitizedHtml(row.html)}
                />
              ) : (
                <span className="min-w-0 whitespace-pre-line break-words font-medium">
                  {row.text}
                </span>
              )}
            </div>
          ))}
        </div>
        {closing && (
          <div
            className={cn(TERMS_HTML_CLASS, 'border-t border-border pt-4')}
            dangerouslySetInnerHTML={sanitizedHtml(closing)}
          />
        )}
      </CardContent>
    </Card>
  );
}
