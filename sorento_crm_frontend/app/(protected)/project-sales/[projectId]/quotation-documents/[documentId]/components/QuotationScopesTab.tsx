'use client';

import * as React from 'react';
import Link from 'next/link';
import { SquarePen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useQuotations } from '../../../../_shared/hooks/useProjects';
import { useQuotationFeedback } from '../../../../_shared/hooks/useQuotationDocuments';
import { QuotationVersionEditor } from '../../../components/QuotationVersionEditor';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';
import { isLockedForApproval } from '../../../../_shared/lib/quotationDecision';
import { QuotationScopeTabs } from './QuotationScopeTabs';

/**
 * The lines, under the letterhead on the Header tab (PROPOSAL-HEADER-LAYOUT, owner 5 Nov 2026:
 * "for quotation I think the lines better be same page with Header"): the area strip and the
 * priced lines under whichever area is open.
 *
 * A READ (#1341). The owner: "editing of scope should be done by 'Edit Quotation', not a separate
 * button like this, Edit quotation means I edit the whole quotation". So there is no per-scope
 * Edit scope, no instant Add a scope and no "Press Edit" hint: a scope's name, series and lines
 * change in the form page opened from the gear.
 *
 * No row above the lines either (owner, 5 Nov 2026): the area's name is already its open tab, the
 * version is the chip in the record header, and Recheck alerts / Revise are gear items there.
 * Record outcome is not on this page at all ("we only need per project outcome"; its own lane).
 *
 * The document itself is not fetched here - it comes from the layout, so the tabs cannot end up
 * with two answers about the same quotation.
 */
export function QuotationScopesTab() {
  const {
    projectId,
    documentId,
    document: record,
    project,
    canEdit,
    activeScopeId,
    selectScope,
    versionNo,
    recheckResults,
    dismissRecheck,
    lineFlags,
    setLineFlags,
  } = useQuotationDocumentScreen();
  const quotations = useQuotations(projectId);


  // Open customer feedback, marked on the lines it names (PS-QUOTE-MATRIX, mock frame 5). The
  // same query as the Customer feedback tab and its badge.
  const feedback = useQuotationFeedback(projectId, documentId);
  const openFeedback = React.useMemo(
    () =>
      (feedback.data?.requests ?? []).flatMap((request) =>
        request.rows.filter((row) => !row.handled_at),
      ),
    [feedback.data],
  );

  const scopes = record.scopes ?? [];
  const activeScope =
    scopes.find((scope) => scope.id === activeScopeId) ?? scopes[0] ?? null;
  const activeQuotation =
    (quotations.data ?? []).find((row) => row.id === activeScope?.id) ?? null;

  if (scopes.length === 0) {
    // Rendered, never hidden: a quotation with no scopes is a real state. Its next step is the
    // form page, where scopes and their lines are added and saved together.
    return (
      <Card>
        <CardContent className="px-6 py-10 text-center">
          <h3 className="text-sm font-semibold">
            No lines on this quotation yet
          </h3>
          {canEdit && (
            <Button asChild variant="outline" size="sm" className="mt-4">
              <Link
                href={`/project-sales/${projectId}/quotation-documents/${documentId}/edit`}
              >
                <SquarePen className="size-4" aria-hidden />
                Edit quotation
              </Link>
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <QuotationScopeTabs
        scopes={scopes}
        activeScopeId={activeScope?.id ?? ''}
        onSelect={selectScope}
        canEdit={canEdit}
      />

      {activeQuotation ? (
        <Card>
          {/* min-w-0 is load-bearing: CardContent is a flex item, and without it the line grid
              stretches the Card and the whole PAGE scrolls sideways at phone width. */}
          <CardContent className="min-w-0 py-5">
            {/* Keyed by scope so switching tabs gives the editor a clean instance rather than one
                still holding the previous scope's selected version. */}
            <QuotationVersionEditor
              key={activeQuotation.id}
              project={project}
              quotation={activeQuotation}
              // Pending or approved: the whole quotation is locked, and the way out is the
              // header's Edit quotation (Revise with a reason), not a per-scope revise.
              locked={isLockedForApproval(record)}
              feedback={openFeedback}
              flagFilter={{ value: lineFlags, onChange: setLineFlags }}
              headerVersion={{
                versionNo,
                // Keyed by the version id each recheck ran on; the editor shows the one for the
                // version it is reading, so a frozen version never shows the current one's answer.
                recheckResults,
                onDismissRecheck: dismissRecheck,
              }}
            />
          </CardContent>
        </Card>
      ) : quotations.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <h3 className="text-sm font-semibold">
              This scope could not be opened
            </h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              Its lines are not available right now. Reload the page to try
              again.
            </p>
          </CardContent>
        </Card>
      )}

    </div>
  );
}
