'use client';

import * as React from 'react';
import Link from 'next/link';
import { Download, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';
import { QuotationScopeTabs } from './QuotationScopeTabs';
import { QuotationScopeTable } from './QuotationScopeTable';
import { QuotationSectionDialog } from './QuotationSectionDialog';
import { QuotationCoverLetterPanel, QuotationTermsPanel } from './QuotationLetterPanels';
import { QuotationSignatureBlock } from './QuotationSignatureBlock';
import {
  MOCK_DOCUMENT,
  MOCK_STATUSES,
  MOCK_TRANSITIONS,
  documentTotal,
} from './documentMocks';
import { documentMoves, splitDocumentMoves } from './documentStatusMoves';

/**
 * PHASE 1 PROTOTYPE. Mock data only, no endpoint behind any of it.
 *
 * What it exists to settle, before a single table is created: whether ONE quotation carrying
 * several scopes as tabs, with the letterhead the printed document has and the total under the
 * column it sums, is the shape the client meant.
 *
 * The page header follows the system's own rule and nothing else: ONE primary CTA, derived from
 * the status graph, and every other action behind the gear. Download PDF is not a call to action,
 * it is a thing you can also do; "Issue R3" is not a hardcoded button, it is whatever the graph
 * says the next rung is. The total moved down into the letterhead beside the date, where it reads
 * as a fact about the document instead of competing with the action.
 *
 * The state switcher at the top is prototype furniture and does not ship. It is here because a
 * screen reviewed only in its happy state gets rebuilt when the empty one turns out to be ugly.
 */
type PrototypeState = 'data' | 'loading' | 'empty' | 'error';

const STATES: { key: PrototypeState; label: string }[] = [
  { key: 'data', label: 'Priced' },
  { key: 'loading', label: 'Loading' },
  { key: 'empty', label: 'No scopes yet' },
  { key: 'error', label: 'Failed to load' },
];

export function QuotationDocumentPrototype({ projectId }: { projectId: string }) {
  const [state, setState] = React.useState<PrototypeState>('data');
  const [activeScopeId, setActiveScopeId] = React.useState(MOCK_DOCUMENT.scopes[0].id);
  const [sectionDialog, setSectionDialog] = React.useState<{ label: string | null } | null>(
    null,
  );

  const document = MOCK_DOCUMENT;
  const scopes = state === 'empty' ? [] : document.scopes;
  const activeScope = scopes.find((scope) => scope.id === activeScopeId) ?? scopes[0] ?? null;
  const grandTotal = state === 'empty' ? 0 : documentTotal(document);

  const currentStatus = MOCK_STATUSES.find((status) => status.id === document.status_id);
  const { primary, secondary } = splitDocumentMoves(
    documentMoves(MOCK_STATUSES, MOCK_TRANSITIONS, document.status_id),
  );

  return (
    <div className="space-y-5 pb-24">
      <div className="rounded-lg border border-dashed border-border bg-muted/30 px-4 py-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            Prototype on sample data from Cabana Elmina R2. Nothing here is saved.
          </p>
          <div className="flex flex-wrap gap-1">
            {STATES.map((option) => (
              <Button
                key={option.key}
                type="button"
                size="sm"
                variant={state === option.key ? 'primary' : 'outline'}
                onClick={() => setState(option.key)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">{document.document_no}</span>
            {currentStatus && (
              <Badge variant="info" appearance="light">
                {currentStatus.label}
              </Badge>
            )}
          </div>
          <h1 className="mt-1 break-words text-xl font-semibold">{document.subject_title}</h1>
          <p className="text-sm text-muted-foreground">{document.recipient.name}</p>
        </div>

        {/* One CTA, then the gear. The move the graph calls next is the button; corrections,
            exits and exports live behind the gear so the header states one intent. */}
        <div className="flex flex-wrap items-center gap-2">
          {primary && (
            <Button type="button" size="sm">
              {primary.label}
            </Button>
          )}
          <DetailActionsMenu ariaLabel="Quotation actions">
            <DropdownMenuItem>
              <Download className="size-4" aria-hidden />
              Download PDF
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Download className="size-4" aria-hidden />
              Download Excel
            </DropdownMenuItem>
            {secondary.length > 0 && <DropdownMenuSeparator />}
            {secondary.map((move) => (
              <DropdownMenuItem key={move.transitionId}>{move.label}</DropdownMenuItem>
            ))}
          </DetailActionsMenu>
        </div>
      </header>

      {state === 'error' ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            This quotation could not be loaded
          </h2>
          <Button asChild variant="outline" className="mt-4">
            <Link href={`/project-sales/${projectId}?tab=quotations`}>Back to quotations</Link>
          </Button>
        </div>
      ) : state === 'loading' ? (
        <div className="space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-10 w-72" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <>
          <QuotationDocumentHeader document={document} grandTotal={grandTotal} />

          {scopes.length === 0 ? (
            // Rendered, never hidden: a quotation with no scopes is a real state on the way to a
            // priced one. The way in stays TOP-RIGHT with the other one, so a reader learns one
            // place for it rather than a centred button that exists only while the list is empty.
            <>
              <div className="flex justify-end">
                <Button type="button" variant="outline" size="sm">
                  <Plus className="size-4" aria-hidden />
                  Add a scope
                </Button>
              </div>
              <Card>
                <CardContent className="px-6 py-10 text-center">
                  <h3 className="text-sm font-semibold">No scopes on this quotation yet</h3>
                  <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                    A scope is a part of the development priced on its own - the townhouses, the
                    guard house, the reception.
                  </p>
                </CardContent>
              </Card>
            </>
          ) : (
            <>
              <QuotationScopeTabs
                scopes={scopes}
                activeScopeId={activeScope?.id ?? ''}
                onSelect={setActiveScopeId}
                canEdit
                onAddScope={() => undefined}
              />

              {activeScope && (
                <QuotationScopeTable
                  scope={activeScope}
                  canEdit
                  onAddLine={() => undefined}
                  onAddSection={() => setSectionDialog({ label: null })}
                  onEditSection={(label) => setSectionDialog({ label })}
                />
              )}
            </>
          )}

          <QuotationCoverLetterPanel
            letter={document.cover_letter}
            canEdit
            onEdit={() => undefined}
          />
          <QuotationTermsPanel terms={document.terms} />
          <QuotationSignatureBlock document={document} canEdit onSign={() => undefined} />
        </>
      )}

      {sectionDialog && (
        <QuotationSectionDialog
          open
          onOpenChange={(next) => {
            if (!next) setSectionDialog(null);
          }}
          initialLabel={sectionDialog.label}
          onSave={() => setSectionDialog(null)}
          onDelete={sectionDialog.label ? () => setSectionDialog(null) : undefined}
        />
      )}
    </div>
  );
}
