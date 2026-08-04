'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Download, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import {
  useQuotationDocument,
  useQuotationDocumentMutations,
} from '../../../../_shared/hooks/useQuotationDocuments';
import { useProject, useQuotations } from '../../../../_shared/hooks/useProjects';
import { OutcomePill } from '../../../../_shared/components/OutcomePill';
import { QuotationOutcomeDialog } from '../../../components/QuotationOutcomeDialog';
import { QuotationVersionEditor } from '../../../components/QuotationVersionEditor';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';
import { QuotationScopeTabs } from './QuotationScopeTabs';
import { QuotationNameDialog } from './QuotationNameDialog';
import { QuotationCoverLetterPanel, QuotationTermsPanel } from './QuotationLetterPanels';
import { QuotationSignatureBlock } from './QuotationSignatureBlock';

/**
 * One quotation DOCUMENT: the letterhead the customer receives, and the scopes priced under it.
 *
 * The layout is the prototype's, signed off with the client, now driven by the real document.
 * The header follows the system's own rule and nothing else: ONE primary CTA, and every other
 * action behind the gear. Download is not a call to action, it is a thing you can also do;
 * issuing is the move that changes what the customer holds.
 *
 * The scope's LINES are not rebuilt here. Lines hang off a version, the version editor already
 * owns that, and a second line table would eventually disagree with it about what is frozen.
 */
export function QuotationDocumentClient({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  const router = useRouter();
  const document = useQuotationDocument(projectId, documentId);
  const project = useProject(projectId);
  // A scope IS a quotation row, and the line editor takes the full record. The project's
  // quotation list is already cached by the tab the user clicked in from, so resolving the
  // open scope through it costs nothing on the usual path.
  const quotations = useQuotations(projectId);
  const mutations = useQuotationDocumentMutations(projectId, documentId);

  const [activeScopeId, setActiveScopeId] = React.useState<string | null>(null);
  const [decidingScopeId, setDecidingScopeId] = React.useState<string | null>(null);
  const [addingScope, setAddingScope] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  const scopes = document.data?.scopes ?? [];
  const activeScope = scopes.find((scope) => scope.id === activeScopeId) ?? scopes[0] ?? null;
  const activeQuotation =
    (quotations.data ?? []).find((row) => row.id === activeScope?.id) ?? null;

  if (document.isLoading || project.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (document.isError || !document.data || !project.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This quotation could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {document.error instanceof Error ? document.error.message : 'It may have been deleted.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}?tab=quotations`}>Back to quotations</Link>
        </Button>
      </div>
    );
  }

  const record = document.data;
  const canEdit = project.data.can_edit;
  // R1 on a document nobody has issued, R3 on one that stands at R2. One expression for both:
  // the next revision is always the one after whatever the customer currently holds.
  const nextIssueNo = (record.current_issue_no ?? 0) + 1;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">{record.document_no}</span>
            <Badge variant={record.is_issued ? 'success' : 'secondary'} appearance="light">
              {record.is_issued ? 'Issued' : 'Draft'}
            </Badge>
          </div>
          <h1 className="mt-1 break-words text-xl font-semibold">
            {record.subject_title ?? '-'}
          </h1>
          <p className="break-words text-sm text-muted-foreground">
            {record.recipient_name_snapshot ?? '-'}
          </p>
        </div>

        {/* One CTA, then the gear. Issuing is the move; exports and the delete live behind the
            gear so the header states one intent. */}
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && (
            <Button
              type="button"
              size="sm"
              disabled={mutations.issue.isPending}
              onClick={() => mutations.issue.mutate(documentId)}
            >
              {`Issue R${nextIssueNo}`}
            </Button>
          )}
          <DetailActionsMenu ariaLabel="Quotation actions">
            {/* Disabled rather than absent: the client asked for both exports, and a menu that
                simply lacks them reads as "this system cannot do it". */}
            <DropdownMenuItem disabled>
              <Download className="size-4" aria-hidden />
              <span className="min-w-0">
                Download PDF
                <span className="block text-xs text-muted-foreground">Not built yet</span>
              </span>
            </DropdownMenuItem>
            <DropdownMenuItem disabled>
              <Download className="size-4" aria-hidden />
              <span className="min-w-0">
                Download Excel
                <span className="block text-xs text-muted-foreground">Not built yet</span>
              </span>
            </DropdownMenuItem>
            {canEdit && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
                  <Trash2 className="size-4" aria-hidden />
                  Delete quotation
                </DropdownMenuItem>
              </>
            )}
          </DetailActionsMenu>
        </div>
      </header>

      <QuotationDocumentHeader document={record} />

      {scopes.length === 0 ? (
        // Rendered, never hidden: a quotation with no scopes is a real state on the way to a
        // priced one. The way in stays TOP-RIGHT with the other one, so a reader learns one
        // place for it rather than a centred button that exists only while the list is empty.
        <>
          {canEdit && (
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setAddingScope(true)}
              >
                <Plus className="size-4" aria-hidden />
                Add a scope
              </Button>
            </div>
          )}
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
            canEdit={canEdit}
            onAddScope={() => setAddingScope(true)}
          />

          {activeQuotation ? (
            <Card>
              {/* The scope's own commercial result, beside the lines it applies to.
                  Outcome is per SCOPE and the project's outcome is derived from it, so losing
                  this control would leave a project permanently open with no way to say the
                  townhouse was won. It used to live on the per-scope page, which the document
                  screen replaced as the way in. */}
              <CardHeader className="flex flex-col items-start gap-3 border-b border-border sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <CardTitle className="min-w-0 break-words text-sm">
                    {activeQuotation.scope_label}
                  </CardTitle>
                  <OutcomePill outcome={activeQuotation.outcome} />
                  {activeQuotation.loss_reason_label && (
                    <span className="text-xs text-muted-foreground">
                      {activeQuotation.loss_reason_label}
                    </span>
                  )}
                </div>
                {canEdit && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setDecidingScopeId(activeQuotation.id)}
                  >
                    Record outcome
                  </Button>
                )}
              </CardHeader>
              <CardContent className="py-5">
                <QuotationVersionEditor project={project.data} quotation={activeQuotation} />
              </CardContent>
            </Card>
          ) : quotations.isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <Card>
              <CardContent className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold">This scope could not be opened</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Its lines are not available right now. Reload the page to try again.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}

      <QuotationCoverLetterPanel html={record.cover_letter_html} />
      <QuotationTermsPanel html={record.terms_html} />
      <QuotationSignatureBlock document={record} />

      {decidingScopeId && activeQuotation && project.data && (
        <QuotationOutcomeDialog
          project={project.data}
          quotation={activeQuotation}
          onDone={() => setDecidingScopeId(null)}
        />
      )}

      <QuotationNameDialog
        open={addingScope}
        onOpenChange={setAddingScope}
        initialLabel={null}
        addTitle="Add a scope"
        renameTitle="Rename scope"
        fieldLabel="Scope name"
        placeholder="e.g. Townhouse, Guard house"
        hint="A part of the development priced on its own."
        isSaving={mutations.addScope.isPending}
        onSave={async (label) => {
          try {
            const scope = await mutations.addScope.mutateAsync({
              id: documentId,
              scopeLabel: label,
            });
            setAddingScope(false);
            // Land on what was just added rather than on whichever tab was open before.
            setActiveScopeId(scope.id);
          } catch {
            // The mutation already toasted the reason. The dialog stays open holding the typed
            // name, so a rejected label can be corrected rather than retyped.
          }
        }}
      />

      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Confirm delete"
        description={`Delete quotation ${record.document_no} and all ${scopes.length} of its scopes? This action cannot be undone.`}
        onDelete={async () => {
          await mutations.remove.mutateAsync(documentId);
        }}
        onSuccess={() => router.push(`/project-sales/${projectId}?tab=quotations`)}
        successMessage="Quotation deleted"
      />
    </div>
  );
}
