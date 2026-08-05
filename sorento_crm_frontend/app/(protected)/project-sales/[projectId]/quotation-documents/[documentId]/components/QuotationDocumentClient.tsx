'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Download, Link2, PenLine, SquarePen, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import {
  useQuotationDocument,
  useQuotationDocumentMutations,
  useQuotationIssues,
} from '../../../../_shared/hooks/useQuotationDocuments';
import {
  useProject,
  useProjectQuotationVersions,
  useQuotationBulkLineMutation,
  useQuotationMutations,
  useQuotations,
} from '../../../../_shared/hooks/useProjects';
import { sumMoney } from '../../../components/POIntakeMoney';
import {
  stagedLinesToBody,
  stagedScopeTotal,
  unfinishedStagedLines,
} from '../../../components/QuotationVersionEditor';
import { QuotationDocumentHeader } from './QuotationDocumentHeader';
import { QuotationDocumentProvider } from './QuotationDocumentContext';
import { QuotationDocumentTabs } from './QuotationDocumentTabs';
import { QuotationSignDialog } from './QuotationSignDialog';
import { QuotationSignLinkDialog } from './QuotationSignLinkDialog';
import { ReviseToEditDialog } from './ReviseToEditDialog';
import { useQuotationEditSession } from './useQuotationEditSession';

/**
 * One quotation DOCUMENT: the letterhead the customer receives, and the tabs it is read through.
 *
 * This is the shell every tab renders inside. The identity of the record - its ref, who it is to,
 * its total, the one CTA and the gear - sits ABOVE the tabs and stays on screen wherever the
 * reader goes, because it is what the record IS rather than one section of it.
 *
 * The header follows the system's own rule and nothing else: ONE primary CTA, and every other
 * action behind the gear. Download is not a call to action, it is a thing you can also do;
 * issuing is the move that changes what the customer holds.
 *
 * The document is fetched HERE, once, and handed to the tabs through context. Fetching it per tab
 * would let two tabs hold two versions of one quotation, and this is also the only place state can
 * live that has to survive a tab switch: routed tabs unmount their panels on the way out.
 */
export function QuotationDocumentClient({
  projectId,
  documentId,
  children,
}: {
  projectId: string;
  documentId: string;
  /** The open tab, routed in by the layout. */
  children?: React.ReactNode;
}) {
  const router = useRouter();
  const document = useQuotationDocument(projectId, documentId);
  const project = useProject(projectId);
  // Newest first, so [0] is the revision the customer currently holds - the one whose PDF and
  // counter-sign link are the ones worth handing out.
  const issues = useQuotationIssues(projectId, documentId);
  const mutations = useQuotationDocumentMutations(projectId, documentId);
  /**
   * Which scopes are still open for editing, straight from the server's own `is_editable`.
   *
   * Read here rather than inside the Scopes panel because Edit sits in this header and is on
   * screen from every tab. Both queries are the ones the Scopes panel and the line editor already
   * use, so react-query answers them from cache on the usual path.
   */
  const quotations = useQuotations(projectId);
  const scopeVersions = useProjectQuotationVersions(quotations.data);
  const quotationMutations = useQuotationMutations(projectId);
  const bulkLines = useQuotationBulkLineMutation(projectId);
  const edit = useQuotationEditSession();

  const [activeScopeId, setActiveScopeId] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [signing, setSigning] = React.useState(false);
  const [linkToShow, setLinkToShow] = React.useState<string | null>(null);
  const [revisePrompt, setRevisePrompt] = React.useState(false);
  const [confirmRemovals, setConfirmRemovals] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);

  const selectScope = React.useCallback((scopeId: string) => setActiveScopeId(scopeId), []);

  // Memoised because the total below is: `?? []` mints a new array whenever the document has no
  // scopes, which would re-sum the header on every render of the page.
  const documentScopes = document.data?.scopes;
  const scopes = React.useMemo(() => documentScopes ?? [], [documentScopes]);

  /**
   * The document total with every staged scope's own figure in place of its saved one.
   *
   * Derived HERE, from the staged drafts the shell already holds, rather than being reported
   * upwards by whichever editor happens to be mounted. That report needed a matching cleanup on
   * unmount, which is two mechanisms for one number and the reason a tab switch used to snap the
   * header back to a figure the screen no longer agreed with.
   *
   * Summed with the repo's decimal-exact helper over STRINGS - `parseFloat` on 52 two-decimal
   * values drifts, and a cent of drift on a quotation total is the kind of disagreement the
   * customer notices. `null` (the helper's answer to anything that is not a plain decimal) falls
   * the header back to the server's own `grand_total`.
   */
  const stagedScopes = edit.scopes;
  const liveGrandTotal = React.useMemo(() => {
    if (Object.keys(stagedScopes).length === 0) return null;
    return sumMoney(
      scopes.map(
        (scope) =>
          (stagedScopes[scope.id] ? stagedScopeTotal(stagedScopes[scope.id].lines) : null) ??
          scope.scope_total,
      ),
    );
  }, [scopes, stagedScopes]);

  /**
   * Every scope whose current version is frozen, so Edit knows whether it is about to change
   * this quotation or to open the next one.
   *
   * `is_editable` from the server, never `is_current`: an issued version is still the highest
   * one until somebody revises. And never the document's `is_issued` either, which stays true
   * for good and would keep offering a revision to somebody who has already opened one.
   */
  const lockedScopes = React.useMemo(() => {
    // Only THIS document's scopes. `quotations.data` is every scope in the PROJECT, across every
    // quotation document, so counting it told a clean single-scope draft that four scopes were
    // with the customer and offered a revision nobody needed.
    const mine = new Set(scopes.map((scope) => scope.id));
    return (quotations.data ?? [])
      .filter((quotation) => mine.has(quotation.id))
      .map((quotation) => ({
        quotation,
        current: scopeVersions.rows.find(
          (row) => row.quotation.id === quotation.id && row.version.is_current,
        )?.version,
      }))
      .filter((pair) => pair.current && !(pair.current.is_editable ?? pair.current.is_current));
  }, [quotations.data, scopeVersions.rows, scopes]);

  /**
   * Warn before the browser throws the staged work away.
   *
   * Only covers leaving the SITE (a refresh, a closed tab, an external link). Moving between this
   * document's own tabs keeps the session, which is the whole reason it lives in the shell.
   */
  const isDirty = edit.isDirty;
  React.useEffect(() => {
    if (!isDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [isDirty]);

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
  const sorentoSignature = record.signatory_signature ?? null;
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

  /**
   * What the header says about the state it is in, reason and next action together.
   *
   * The screen used to state a fact and stop there ("The customer holds this version, so its
   * lines cannot be changed"), and the client read it and still asked why they could not edit.
   * Every line here names the way forward as well as the reason.
   */
  const headerHints: string[] = [];
  if (edit.isEditing) {
    headerHints.push('Nothing is written until you press Save.');
  } else {
    if (!canEdit) {
      headerHints.push('You can read this quotation but not change it.');
    } else if (lockedScopes.length > 0) {
      headerHints.push('The customer holds this version. Edit opens the next one.');
    }
    if (canEdit && !isSigned) headerHints.push('Sign it first');
  }

  /**
   * Edit. On a quotation the customer holds it asks first, because the answer is a revision.
   */
  function startEditing() {
    if (lockedScopes.length > 0) {
      setRevisePrompt(true);
      return;
    }
    edit.begin();
  }

  async function reviseThenEdit() {
    try {
      // Sequentially, not in parallel: each revise reads and freezes the scope's current
      // version, and the failure of one must not leave the rest half-opened behind a spinner.
      for (const pair of lockedScopes) {
        await quotationMutations.revise.mutateAsync(pair.quotation.id);
      }
      setRevisePrompt(false);
      edit.begin();
    } catch {
      // The mutation toasted the reason. The dialog stays open so it can be tried again.
    }
  }

  /**
   * The whole quotation in one write: the lines of every scope that was touched, then the
   * letterhead prose.
   *
   * ONE request per scope, not one per line. That is the client's complaint answered - "every
   * addition of line doesn't trigger a save" - and it also makes a Save atomic per scope: either
   * the arrangement they made is what is stored, or nothing moved.
   */
  async function runSave() {
    setIsSaving(true);
    try {
      for (const scope of edit.changedScopes) {
        await bulkLines.mutateAsync({
          versionId: scope.versionId,
          lines: stagedLinesToBody(scope.lines),
        });
      }

      const wroteDocument = Object.keys(edit.documentDraft).length > 0;
      if (wroteDocument) {
        await mutations.update.mutateAsync({ id: documentId, body: edit.documentDraft });
      }

      edit.cancel();
      // The document PATCH raises its own "Quotation saved". Two notifications for one button
      // press is the same noise the per-line toasts were removed for.
      if (!wroteDocument) toast.success('Quotation saved');
    } catch {
      // Every mutation already toasted the reason, and the session is deliberately left open:
      // what was typed is still on screen and still saveable.
    } finally {
      setIsSaving(false);
    }
  }

  function requestSave() {
    // A line the server would refuse is caught here rather than half-way through a save that
    // has already rewritten another scope. The cell is already marked; this says how many.
    const unfinished = edit.changedScopes.reduce(
      (total, scope) => total + unfinishedStagedLines(scope.lines),
      0,
    );
    if (unfinished > 0) {
      toast.error(
        unfinished === 1
          ? 'One line still needs a product or a description.'
          : `${unfinished} lines still need a product or a description.`,
      );
      return;
    }
    // The one confirmation of the whole edit view. Staging a removal destroyed nothing, so it
    // asked nothing; this is the moment lines actually leave the quotation.
    if (edit.removedCount > 0) {
      setConfirmRemovals(true);
      return;
    }
    void runSave();
  }

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
            while it is the thing standing in the way.

            In an edit session the header states ONE intent too, and it is a different one: Save
            and Cancel, with signing and issuing out of the way until the changes have landed. */}
        <div className="flex flex-col items-stretch gap-1.5 sm:items-end">
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && edit.isEditing && (
              <>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={isSaving}
                  onClick={() => edit.cancel()}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  size="sm"
                  disabled={isSaving || !edit.isDirty}
                  title={edit.isDirty ? undefined : 'Nothing has changed yet'}
                  onClick={requestSave}
                >
                  {isSaving ? 'Saving...' : 'Save'}
                </Button>
              </>
            )}
            {canEdit && !edit.isEditing && (
              <Button type="button" size="sm" variant="outline" onClick={startEditing}>
                <SquarePen className="size-4" aria-hidden />
                Edit
              </Button>
            )}
            {canEdit && !edit.isEditing && !isSigned && (
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
            {canEdit && !edit.isEditing && (
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
          {/* Why the screen is in the state it is in, and what to do about it, in one sentence.
              The old copy stated a fact and offered no move, which is what the client read and
              still could not act on: "i don't know when can i edit and when i cannot ... this
              line is confusing". Reason and next action, always together. */}
          {/* Visible, not only a tooltip: a disabled button with the reason hidden behind a
              hover is unreadable on the phone this page also has to work on. */}
          {headerHints.map((hint) => (
            <p key={hint} className="text-xs text-muted-foreground sm:text-right">
              {hint}
            </p>
          ))}
        </div>
      </header>

      <QuotationDocumentHeader document={record} liveGrandTotal={liveGrandTotal} />

      <QuotationDocumentTabs projectId={projectId} documentId={documentId} />

      <QuotationDocumentProvider
        value={{
          projectId,
          documentId,
          document: record,
          project: project.data,
          canEdit,
          latestIssue,
          sorentoSignature,
          activeScopeId,
          selectScope,
          edit,
        }}
      >
        {children}
      </QuotationDocumentProvider>

      <QuotationSignDialog
        open={signing}
        onOpenChange={setSigning}
        signatoryName={record.signatory_name}
        isSaving={mutations.sign.isPending}
        onSign={async (body) => {
          try {
            await mutations.sign.mutateAsync({ id: documentId, body });
            setSigning(false);
          } catch {
            // The mutation toasted the reason. The dialog stays open so the signature can be
            // re-applied without reopening it.
          }
        }}
      />

      <QuotationSignLinkDialog url={linkToShow} onOpenChange={() => setLinkToShow(null)} />

      <ReviseToEditDialog
        open={revisePrompt}
        onOpenChange={setRevisePrompt}
        scopeLabels={lockedScopes.map((pair) => pair.quotation.scope_label)}
        nextVersionLabel={
          lockedScopes.length === 1 && lockedScopes[0].current
            ? `v${lockedScopes[0].current.version_no + 1}`
            : null
        }
        isRevising={quotationMutations.revise.isPending}
        onConfirm={reviseThenEdit}
      />

      {/* The edit view's ONE destructive confirmation. Staging a removal destroys nothing and so
          asks nothing; this is the moment the lines actually leave, and it names how many. */}
      <AlertDialog open={confirmRemovals} onOpenChange={setConfirmRemovals}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              {`Saving removes ${edit.removedCount} ${
                edit.removedCount === 1 ? 'line' : 'lines'
              } from this quotation. This action cannot be undone.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSaving}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={isSaving}
              onClick={(event) => {
                // Held open by hand: the dialog closes itself on the click, and the save that
                // follows would then have no place to report a failure back to.
                event.preventDefault();
                void runSave().then(() => setConfirmRemovals(false));
              }}
            >
              {`Save and remove ${edit.removedCount} ${
                edit.removedCount === 1 ? 'line' : 'lines'
              }`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
