'use client';

import * as React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { sanitizedHtml } from '@/lib/sanitize';
import { TERMS_HTML_CLASS } from '@/lib/terms-html';
import type {
  CoverCell,
  CoverPageData,
  CoverSection,
} from '@/lib/quotation-cover';

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

function CellValue({ cell }: { cell: CoverCell }) {
  return cell.html ? (
    <div
      className={cn(TERMS_HTML_CLASS, 'min-w-0')}
      dangerouslySetInnerHTML={sanitizedHtml(cell.html)}
    />
  ) : (
    <span className="block min-w-0 whitespace-pre-line break-words">
      {cell.text}
    </span>
  );
}

/** One column of one section, drawn the way the PDF prints that section's style. */
function SectionColumn({
  section,
  cells,
  start,
  wide,
}: {
  section: CoverSection;
  cells: CoverCell[];
  start: number;
  wide: boolean;
}) {
  if (section.style === 'title') {
    return (
      <div className="min-w-0 space-y-1 text-center text-base font-semibold">
        {cells.map((cell, index) => (
          <CellValue key={index} cell={cell} />
        ))}
      </div>
    );
  }
  if (section.style === 'numbered') {
    return (
      <ol
        start={start}
        className="min-w-0 list-decimal space-y-1.5 pl-5 text-sm"
      >
        {cells.map((cell, index) => (
          <li key={index} className="min-w-0">
            {cell.label && (
              <span className="font-semibold uppercase">{cell.label}: </span>
            )}
            <CellValue cell={cell} />
          </li>
        ))}
      </ol>
    );
  }
  if (section.style === 'footer') {
    return (
      <div className="min-w-0 space-y-0.5 text-xs text-muted-foreground">
        {cells.map((cell, index) => (
          <div key={index} className="flex min-w-0 gap-1">
            {cell.label && <span className="shrink-0">{cell.label}:</span>}
            <CellValue cell={cell} />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="min-w-0 space-y-1.5">
      {section.style === 'signature' && (
        <div
          aria-hidden
          className="h-9 w-full max-w-64 border-b border-foreground"
        />
      )}
      {cells.map((cell, index) => (
        <div
          key={index}
          className={cn(
            'flex min-w-0 text-sm',
            wide ? 'flex-row gap-2' : 'flex-col gap-0.5 sm:flex-row sm:gap-2',
          )}
        >
          {cell.label && (
            <span
              className={cn(
                'shrink-0 text-muted-foreground',
                wide ? 'w-28' : 'sm:w-28',
              )}
            >
              {cell.label}
            </span>
          )}
          <span className="min-w-0 font-medium">
            <CellValue cell={cell} />
          </span>
        </div>
      ))}
    </div>
  );
}

/** A layout 4 cover's sections: a band heading over the section's columns. */
export function CoverSections({
  sections,
  wide = false,
}: {
  sections: CoverSection[];
  wide?: boolean;
}) {
  return (
    <div className="space-y-4" data-testid="cover-sections">
      {sections.map((section, index) => {
        let start = 1;
        const starts = section.cells.map((cells) => {
          const at = start;
          start += cells.length;
          return at;
        });
        return (
          <section
            key={index}
            aria-label={section.label || undefined}
            data-style={section.style}
            className={cn(
              'min-w-0 space-y-2',
              section.style === 'footer' && 'border-t border-border pt-3',
            )}
          >
            {section.label &&
              (section.style === 'signature' ? (
                <p className="text-sm">{section.label}</p>
              ) : (
                <p className="bg-foreground px-2 py-0.5 text-sm font-semibold text-background">
                  {section.label}
                </p>
              ))}
            <div
              className={cn(
                'grid min-w-0 gap-x-6 gap-y-3',
                wide
                  ? 'grid-cols-[repeat(var(--cover-cols),minmax(0,1fr))]'
                  : 'grid-cols-1 sm:grid-cols-[repeat(var(--cover-cols),minmax(0,1fr))]',
              )}
              style={{ '--cover-cols': section.columns } as React.CSSProperties}
            >
              {section.cells.map((cells, column) => (
                <SectionColumn
                  key={column}
                  section={section}
                  cells={cells}
                  start={starts[column]}
                  wide={wide}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/**
 * The cover page: letterhead, title, intro, the label/value rows and closing, in the order the
 * PDF's first page prints them. The one component behind the customer sign link, the quotation's
 * Cover letter tab and the designer preview. A payload with no `cover_title` is the fixed #2088
 * cover (letterhead and rows only); one with `cover_sections` is a layout 4 cover.
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
          <SenderRow
            name={cover.sender_name}
            logoUrl={cover.sender_logo_url}
            noun={noun}
          />
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
        {cover.cover_sections ? (
          <div
            className={cn(
              (letterhead || title || intro) && 'border-t border-border pt-4',
            )}
          >
            <CoverSections sections={cover.cover_sections} wide={wide} />
          </div>
        ) : (
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
                  wide
                    ? 'flex-row gap-2'
                    : 'flex-col gap-1 sm:flex-row sm:gap-2',
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
        )}
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
