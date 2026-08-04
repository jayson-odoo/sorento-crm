'use client';

import * as React from 'react';
import Link from 'next/link';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatMyr } from '../../components/QuotationsPanel';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';
import { QuotationScopeTable } from './QuotationScopeTable';
import { QuotationCoverLetterPanel, QuotationTermsPanel } from './QuotationLetterPanels';
import { QuotationSignatureBlock } from './QuotationSignatureBlock';
import { MOCK_DOCUMENT, documentTotal, scopeTotal } from './documentMocks';

/**
 * PHASE 1 PROTOTYPE. Mock data only, no endpoint behind any of it.
 *
 * What it exists to settle, before a single table is created: whether ONE quotation carrying
 * several scopes as tabs, with the letterhead the printed document has and the total under the
 * column it sums, is the shape the client meant. Their words: "got a header as like the excel,
 * then can add multiple tabs (meaning add multiple scope), then in each scope can add lines,
 * then the total we should always put at the bottom of the corresponding column".
 *
 * The state switcher at the top is prototype furniture and does not ship. It is here because a
 * screen reviewed only in its happy state gets rebuilt when the empty one turns out to be
 * ugly - loading, empty and error each have to be looked at before the backend is written.
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

  const document = MOCK_DOCUMENT;
  const scopes = state === 'empty' ? [] : document.scopes;
  const activeScope = scopes.find((scope) => scope.id === activeScopeId) ?? scopes[0] ?? null;
  const grandTotal = state === 'empty' ? 0 : documentTotal(document);

  const statusTone =
    document.status === 'accepted' ? 'success' : document.status === 'issued' ? 'info' : 'secondary';

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
            <Badge variant={statusTone} appearance="light" className="capitalize">
              {document.status}
            </Badge>
          </div>
          <h1 className="mt-1 break-words text-xl font-semibold">{document.subject_title}</h1>
          <p className="text-sm text-muted-foreground">{document.recipient.name}</p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          {/* The grand total across every scope, which is the sample's TOTAL AMOUNT. */}
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Grand total</p>
            <p className="text-lg font-semibold tabular-nums">{formatMyr(String(grandTotal))}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm">
              Download PDF
            </Button>
            <Button type="button" size="sm">
              Issue R3
            </Button>
          </div>
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
          <QuotationDocumentHeader document={document} />

          {scopes.length === 0 ? (
            // Rendered, never hidden: a quotation with no scopes is a real state on the way to
            // a priced one, and it has to say what to do next rather than look broken.
            <Card>
              <CardContent className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold">No scopes on this quotation yet</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  A scope is a part of the development priced on its own - the townhouses, the
                  guard house, the reception.
                </p>
                <Button type="button" className="mt-4">
                  <Plus className="size-4" aria-hidden />
                  Add a scope
                </Button>
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <Tabs
                  value={activeScope?.id}
                  onValueChange={setActiveScopeId}
                  className="min-w-0"
                >
                  <TabsList className="flex-wrap">
                    {scopes.map((scope) => (
                      <TabsTrigger key={scope.id} value={scope.id}>
                        <span className="truncate">{scope.label}</span>
                        <span className="ms-2 text-xs tabular-nums text-muted-foreground">
                          {formatMyr(String(scopeTotal(scope)))}
                        </span>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
                <Button type="button" variant="outline" size="sm">
                  <Plus className="size-4" aria-hidden />
                  Add a scope
                </Button>
              </div>

              {activeScope && (
                <QuotationScopeTable scope={activeScope} canEdit onAddLine={() => undefined} />
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
    </div>
  );
}
