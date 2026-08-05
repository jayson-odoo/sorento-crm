'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Download, Link2, PenLine, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
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
  useQuotationIssues,
} from '../../../../_shared/hooks/useQuotationDocuments';
import { useProject, useQuotations } from '../../../../_shared/hooks/useProjects';
import { sumMoney } from '../../../components/POIntakeMoney';
import type { QuotationSignatureRecord } from '../../../../_shared/services/quotationDocumentService';
import { OutcomePill } from '../../../../_shared/components/OutcomePill';
import { QuotationOutcomeDialog } from '../../../components/QuotationOutcomeDialog';
import { QuotationVersionEditor } from '../../../components/QuotationVersionEditor';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';
import { QuotationScopeTabs } from './QuotationScopeTabs';
import { QuotationNameDialog } from './QuotationNameDialog';
import { QuotationCoverLetterPanel, QuotationTermsPanel } from './QuotationLetterPanels';
import { QuotationSignatureBlock } from './QuotationSignatureBlock';
import { QuotationSignDialog } from './QuotationSignDialog';
import { QuotationSignLinkDialog } from './QuotationSignLinkDialog';

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
  // Newest first, so [0] is the revision the customer currently holds - the one whose PDF and
  // counter-sign link are the ones worth handing out.
  const issues = useQuotationIssues(projectId, documentId);
  const mutations = useQuotationDocumentMutations(projectId, documentId);

  const [activeScopeId, setActiveScopeId] = React.useState<string | null>(null);
  const [decidingScopeId, setDecidingScopeId] = React.useState<string | null>(null);
  const [addingScope, setAddingScope] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [signing, setSigning] = React.useState(false);
  const [linkToShow, setLinkToShow] = React.useState<string | null>(null);
  /**
   * The signature captured on this page, held here rather than in the query cache.
   *
   * The document GET does not serialize `signatory_signature` yet, so the cache is not a safe home
   * for it: react-query refetches on window focus and would wipe it the first time the user tabbed
   * away. Component state lasts as long as the screen does, which is the whole of the sign-then-
   * issue sequence, and the day the serializer sends the field the line below prefers it.
   */
  const [justSigned, setJustSigned] = React.useState<QuotationSignatureRecord | null>(null);
  /**
   * The open scope's total as the line editor currently has it, including edits the user has
   * typed but not yet saved.
   *
   * Kept per scope, never as a bare figure: a total reported by the townhouse tab must not be
   * spent on the guard house's row when the reader switches tabs.
   */
  const [liveScopeTotal, setLiveScopeTotal] = React.useState<{
    scopeId: string;
    total: string;
  } | null>(null);

  const scopes = document.data?.scopes ?? [];
  const activeScope = scopes.find((scope) => scope.id === activeScopeId) ?? scopes[0] ?? null;
  const activeQuotation =
    (quotations.data ?? []).find((row) => row.id === activeScope?.id) ?? null;

  /**
   * What the line editor calls (as its `onTotalChange`) when the open scope's uncommitted total
   * moves, and `null` when there is nothing live to report.
   *
   * The editor fires it off the same drafts its own footer sums, so the header and the footer
   * cannot drift apart.
   */
  const reportScopeTotal = React.useCallback((scopeId: string, total: string | null) => {
    setLiveScopeTotal(total === null ? null : { scopeId, total });
  }, []);

  function selectScope(scopeId: string) {
    // The figure belonged to the tab being left, so it dies with the switch rather than being
    // carried into another scope's arithmetic.
    reportScopeTotal(scopeId, null);
    setActiveScopeId(scopeId);
  }

  /**
   * The document total with the open scope's live figure substituted for the saved one.
   *
   * Summed with the repo's decimal-exact helper over STRINGS - `parseFloat` on 52 two-decimal
   * values drifts, and a cent of drift on a quotation total is the kind of disagreement the
   * customer notices. `null` (the helper's answer to anything that is not a plain decimal) falls
   * the header back to the server's own `grand_total`.
   */
  const liveGrandTotal =
    liveScopeTotal && scopes.some((scope) => scope.id === liveScopeTotal.scopeId)
      ? sumMoney(
          scopes.map((scope) =>
            scope.id === liveScopeTotal.scopeId ? liveScopeTotal.total : scope.scope_total,
          ),
        )
      : null;

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
  const latestIssue = issues.data?.[0] ?? null;
  const sorentoSignature = record.signatory_signature ?? justSigned;
  /**
   * AC-H1: no signature, no issue. The server refuses an unsigned document with 422
   * `quotation_document_unsigned`, so the CTA says so up front rather than letting somebody
   * press it and read an error.
   *
   * Read off the signature alone. "It is issued, so it must have been signed" looks equivalent
   * and is wrong on any document issued before the gate existed: the button goes live and the
   * server refuses it.
   */
  const isSigned = Boolean(sorentoSignature);

  async function openIssuePdf() {
    if (!latestIssue) return;
    try {
      const blob = await mutations.issuePdf.mutateAsync({
        id: documentId,
        issueId: latestIssue.id,
      });
      const url = URL.createObjectURL(blob);
      // The backend sends it `inline`, so a tab is the intended destination. A blocked popup
      // falls back to saving the file, which is never worse than nothing happening.
      //
      // Deliberately WITHOUT `noopener`: Chrome returns null for a noopener window whether it
      // opened or not, so the null check would fire the download every single time and the user
      // would get a tab AND a file. There is nothing to protect here anyway - a blob: URL has no
      // remote page to hand a window reference to.
      const opened = window.open(url, '_blank');
      if (!opened) {
        const anchor = window.document.createElement('a');
        anchor.href = url;
        anchor.download = `${record.document_no.replace(/\//g, '-')}-R${latestIssue.issue_no}.pdf`;
        window.document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      }
      // Revoked on a timer, not immediately: the new tab has to finish reading the blob first.
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      // The mutation already toasted the reason, including the 503 a host without the native
      // rendering libraries answers with.
    }
  }

  async function saveIssueXlsx() {
    if (!latestIssue) return;
    try {
      const blob = await mutations.issueXlsx.mutateAsync({
        id: documentId,
        issueId: latestIssue.id,
      });
      const url = URL.createObjectURL(blob);
      // Saved, never opened in a tab: no browser renders a workbook, so window.open would show
      // the user a blank tab and then a download anyway.
      const anchor = window.document.createElement('a');
      anchor.href = url;
      anchor.download = `${record.document_no.replace(/\//g, '-')}-R${latestIssue.issue_no}.xlsx`;
      window.document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      // Already toasted by the mutation.
    }
  }

  async function copyCounterSignLink() {
    if (!latestIssue) return;
    try {
      const link = await mutations.signLink.mutateAsync({
        id: documentId,
        issueId: latestIssue.id,
      });
      // The server returns a relative path on purpose; the origin the customer must land on is
      // whichever one this screen is being used from.
      const url = `${window.location.origin}${link.path}`;
      try {
        await navigator.clipboard.writeText(url);
        toast.success('Counter-sign link copied');
      } catch {
        // Clipboard access refused (plain HTTP, or a browser policy). Show the link instead of
        // stranding the user with a failure and no way to get at it.
        setLinkToShow(url);
      }
    } catch {
      // Already toasted by the mutation.
    }
  }

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
            gear so the header states one intent. Sign sits beside it as an outline button only
            while it is the thing standing in the way. */}
        <div className="flex flex-col items-stretch gap-1.5 sm:items-end">
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && !isSigned && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setSigning(true)}
              >
                <PenLine className="size-4" aria-hidden />
                Sign
              </Button>
            )}
            {canEdit && (
              <Button
                type="button"
                size="sm"
                disabled={mutations.issue.isPending || !isSigned}
                title={isSigned ? undefined : 'Sign it first'}
                onClick={() => mutations.issue.mutate(documentId)}
              >
                {`Issue R${nextIssueNo}`}
              </Button>
            )}
            <DetailActionsMenu ariaLabel="Quotation actions">
              {canEdit && (
                <DropdownMenuItem onSelect={() => setSigning(true)}>
                  <PenLine className="size-4" aria-hidden />
                  {isSigned ? 'Sign again' : 'Sign quotation'}
                </DropdownMenuItem>
              )}
              {/* Disabled rather than absent: the client asked for both exports, and a menu that
                  simply lacks them reads as "this system cannot do it". */}
              <DropdownMenuItem
                disabled={!record.is_issued || mutations.issuePdf.isPending}
                onSelect={() => void openIssuePdf()}
              >
                <Download className="size-4" aria-hidden />
                <span className="min-w-0">
                  Download PDF
                  {!record.is_issued && (
                    <span className="block text-xs text-muted-foreground">
                      Issue it first
                    </span>
                  )}
                </span>
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!record.is_issued || mutations.issueXlsx.isPending}
                onSelect={() => void saveIssueXlsx()}
              >
                <Download className="size-4" aria-hidden />
                <span className="min-w-0">
                  Download Excel
                  {!record.is_issued && (
                    <span className="block text-xs text-muted-foreground">
                      Issue it first
                    </span>
                  )}
                </span>
              </DropdownMenuItem>
              {canEdit && (
                <DropdownMenuItem
                  disabled={!record.is_issued || mutations.signLink.isPending}
                  onSelect={() => void copyCounterSignLink()}
                >
                  <Link2 className="size-4" aria-hidden />
                  <span className="min-w-0">
                    Copy counter-sign link
                    {!record.is_issued && (
                      <span className="block text-xs text-muted-foreground">
                        Issue it first
                      </span>
                    )}
                  </span>
                </DropdownMenuItem>
              )}
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
          {canEdit && !isSigned && (
            // Visible, not only a tooltip: a disabled button with the reason hidden behind a
            // hover is unreadable on the phone this page also has to work on.
            <p className="text-xs text-muted-foreground sm:text-right">Sign it first</p>
          )}
        </div>
      </header>

      <QuotationDocumentHeader document={record} liveGrandTotal={liveGrandTotal} />

      {scopes.length === 0 ? (
        // Rendered, never hidden: a quotation with no scopes is a real state on the way to a
        // priced one. The way in is the empty state's own CTA now that adding lives at the end of
        // the tab strip - with no strip on screen there is nowhere else for it to be.
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <h3 className="text-sm font-semibold">No scopes on this quotation yet</h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              A scope is a part of the development priced on its own - the townhouses, the guard
              house, the reception.
            </p>
            {canEdit && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => setAddingScope(true)}
              >
                <Plus className="size-4" aria-hidden />
                Add a scope
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <QuotationScopeTabs
            scopes={scopes}
            activeScopeId={activeScope?.id ?? ''}
            onSelect={selectScope}
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
              {/* min-w-0 is load-bearing. CardContent is a flex item, and a flex item defaults
                  to min-width:auto, so it refuses to shrink below its content: the 1,900px line
                  table then stretched this Card and the whole PAGE scrolled sideways at phone
                  width, instead of the table scrolling inside its own gutter. */}
              <CardContent className="min-w-0 py-5">
                {/* Keyed by scope so switching tabs gives the editor a clean instance rather
                    than one still holding the previous scope's selected version and its
                    last-reported total. Nothing refetches: the versions and lines are already
                    in the query cache. */}
                <QuotationVersionEditor
                  key={activeQuotation.id}
                  project={project.data}
                  quotation={activeQuotation}
                  onTotalChange={(total) => reportScopeTotal(activeQuotation.id, total)}
                />
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
      {/* The counter-signature is read off the LATEST issue, which is the copy the customer is
          holding. An older revision may have been accepted too, but what this panel answers is
          "where does the current quotation stand", and that is the newest one. */}
      <QuotationSignatureBlock
        document={record}
        sorentoSignature={sorentoSignature}
        customerSignature={latestIssue?.customer_signature ?? null}
        acceptedAt={latestIssue?.accepted_at ?? null}
      />

      <QuotationSignDialog
        open={signing}
        onOpenChange={setSigning}
        signatoryName={record.signatory_name}
        isSaving={mutations.sign.isPending}
        onSign={async (body) => {
          try {
            setJustSigned(await mutations.sign.mutateAsync({ id: documentId, body }));
            setSigning(false);
          } catch {
            // The mutation toasted the reason. The dialog stays open so the signature can be
            // re-applied without reopening it.
          }
        }}
      />

      <QuotationSignLinkDialog url={linkToShow} onOpenChange={() => setLinkToShow(null)} />

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
            selectScope(scope.id);
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
