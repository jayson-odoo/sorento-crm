'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, Download, Link2, PenLine, SquarePen, Trash2 } from 'lucide-react';
import { toast } from '@/lib/toast';
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
import DetailActions from '@/components/common/DetailActions';
import { EntityDownloadsButton } from '@/components/my-downloads/EntityDownloadsButton';
import {
  useQuotationApprovalGraph,
  useQuotationDocument,
  useQuotationDocumentMutations,
  useQuotationDocuments,
  useQuotationIssues,
} from '../../../../_shared/hooks/useQuotationDocuments';
import RecordNavigation from '@/components/common/RecordNavigation';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';
import {
  useProject,
  useProjectQuotationVersions,
  useQuotationBulkLineMutation,
  useQuotationMutations,
  useQuotations,
} from '../../../../_shared/hooks/useProjects';
import { quotationStanding } from '../../../../_shared/lib/quotationDecision';
import { sumMoney } from '../../../../_shared/lib/money';
import {
  stagedLinesToBody,
  stagedScopeTotal,
  unfinishedStagedLines,
} from '../../../components/QuotationVersionEditor';
import {
  QuotationApprovalPanel,
  isBlockedByApproval,
} from './QuotationApprovalPanel';
import { QuotationChangesRequestedPanel } from './QuotationChangesRequestedPanel';
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
 * issuing is the move that changes what the customer holds. Edit is behind the gear for the same
 * reason - but only its ENTRY POINT. Once a session is open, Cancel and Save ARE the screen's one
 * intent, and they belong in the header where a control you are about to press can be seen.
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
   * The `quotation` approval graph, so the block below the header can offer the salesperson
   * their own next move by the label the admin gave that edge rather than by a hardcoded one.
   * One install-wide read, cached; it is Setup data, not per-quotation state.
   */
  const approvalGraph = useQuotationApprovalGraph();
  /**
   * Which scopes are still open for editing, straight from the server's own `is_editable`.
   *
   * Read here rather than inside the Scopes panel because Edit sits in this header and is on
   * screen from every tab. Both queries are the ones the Scopes panel and the line editor already
   * use, so react-query answers them from cache on the usual path.
   */
  const quotations = useQuotations(projectId);
  // The project's OTHER quotation documents, for prev/next in the header.
  const siblingDocuments = useQuotationDocuments(projectId);
  // The project's documents are already in memory and unpaged, so the pager is
  // presentational: position and ends computed here.
  const documentIndex = (siblingDocuments.data ?? []).findIndex(
    (row) => row.id === documentId,
  );
  const scopeVersions = useProjectQuotationVersions(quotations.data);
  const quotationMutations = useQuotationMutations(projectId);
  const bulkLines = useQuotationBulkLineMutation(projectId);
  const edit = useQuotationEditSession();

  const [activeScopeId, setActiveScopeId] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [signing, setSigning] = React.useState(false);
  const [linkToShow, setLinkToShow] = React.useState<string | null>(null);
  // The item ticks in place and the menu stays open to be read (S7-05).
  const [signLinkCopied, setSignLinkCopied] = React.useState(false);
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
  /**
   * The document as the SCREEN currently stands: the server's row with whatever header edits are
   * staged merged over it.
   *
   * Merged here, once, rather than per field further down, because three places read the
   * letterhead - the title, the recipient line under it, and the letterhead card - and a session
   * that only reached one of them would have the card saying one recipient while the heading two
   * centimetres above it said another. `documentDraft` only ever holds keys somebody actually
   * typed into, so an untouched field still reads the server's value.
   */
  const shown: QuotationDocument = { ...record, ...edit.documentDraft };
  // Read off the SERVER's record, never off `shown`: where a quotation stands is the customer's
  // answer, not something a half-typed edit session can change.
  const standing = quotationStanding(record);
  // Same gate the letter panels use: a reader with no edit rights never gets a writing surface,
  // even if a session were somehow open.
  const isHeaderEditable = canEdit && edit.isEditing;
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
   * S15: a line priced below its floor cannot go to the customer until a manager says so.
   *
   * The server refuses it with 422 `quotation_below_floor_pending_approval`, and the CTA says
   * so up front rather than letting somebody press it and read an error - exactly how the
   * signature gate above already behaves. The reason and the way to ask for approval are in
   * the panel under the header, because a disabled button with no way forward is a dead end.
   */
  const needsApproval = isBlockedByApproval(record);

  /** What the next copy of a single frozen scope will be called, e.g. "v3". */
  const nextVersionLabel =
    lockedScopes.length === 1 && lockedScopes[0].current
      ? `v${lockedScopes[0].current.version_no + 1}`
      : null;
  /**
   * What pressing the change-request banner's button will actually do, said in its label.
   *
   * Deliberately NOT "Revise to v3": the Scopes tab already carries a per-scope button by that
   * exact name, and two controls reading the same words a few centimetres apart - one acting on
   * one scope, one on the whole document - is worse than a vaguer label. This one is the
   * DOCUMENT's act, and the prompt it opens names the scopes and the version it will mint.
   *
   * With no frozen scope left (a revision is already open) the click goes straight into a
   * session, and the label has to say that rather than promise a version it will not mint.
   */
  const reviseLabel =
    lockedScopes.length === 0 ? 'Edit this quotation' : 'Revise this quotation';

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

  /**
   * Both exports are QUEUED, and neither of them puts a file in front of the user here.
   *
   * They used to render inline and hand the browser a blob: on a long quotation that held the
   * page for as long as WeasyPrint took, which reads as a broken button and was what the client
   * complained about. Now the click leaves a job behind and says so; the file is collected from
   * the printer chip in this header (or the My Downloads drawer) once it is ready, and it can be
   * previewed there rather than downloaded blind.
   */
  async function queueIssuePdf() {
    if (!latestIssue) return;
    try {
      await mutations.issuePdf.mutateAsync({ id: documentId, issueId: latestIssue.id });
    } catch {
      // The mutation already toasted the reason.
    }
  }

  async function queueIssueXlsx() {
    if (!latestIssue) return;
    try {
      await mutations.issueXlsx.mutateAsync({ id: documentId, issueId: latestIssue.id });
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
        setSignLinkCopied(true);
        window.setTimeout(() => setSignLinkCopied(false), 2000);
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
            {/* The SAME reading as the project's quotation list. This badge used to be its own
                `is_issued ? Issued : Draft`, which is why a quotation the customer had accepted
                read "Accepted" in the list and "Issued" here - the two surfaces answered the same
                question differently, which is exactly what `quotationStanding` exists to stop. */}
            <Badge variant={standing.variant} appearance="light">
              {standing.label}
            </Badge>
          </div>
          <h2 className="mt-1 break-words text-xl font-semibold">
            {shown.subject_title ?? '-'}
          </h2>
          <p className="break-words text-sm text-muted-foreground">
            {shown.recipient_name_snapshot ?? '-'}
          </p>
        </div>

        {/* One CTA, then the gear. Issuing is the move; exports and the delete live behind the
            gear so the header states one intent. Sign sits beside it as an outline button only
            while it is the thing standing in the way.

            In an edit session the header states ONE intent too, and it is a different one: Save
            and Cancel, with signing and issuing out of the way until the changes have landed. */}
        <div className="flex flex-col items-stretch gap-1.5 sm:items-end">
          {/* Pager, gear, primary (D6), through the shared group rather than a
              hand-rolled row: the order is the same rule on all 39 detail pages,
              and a copy of it here is a copy that can drift. */}
          <DetailActions
            pagerNode={
              /* Step between this project's quotation documents without going back to the
                  list, the users-detail pattern. List mode off the cached documents query -
                  the list screen the user came from already fetched it, so the neighbours
                  cost nothing. Hidden while editing: stepping away mid-session would look
                  like it discarded the staged lines (it would not - they live in the shell -
                  but a control that LOOKS destructive is one nobody should have to trust).
                  Rendered from two documents up, since with one there is nowhere to go. */
              !edit.isEditing && (siblingDocuments.data ?? []).length > 1 && (
                <RecordNavigation
                  index={documentIndex >= 0 ? documentIndex + 1 : null}
                  total={(siblingDocuments.data ?? []).length}
                  hasPrevious={documentIndex > 0}
                  hasNext={
                    documentIndex >= 0 &&
                    documentIndex < (siblingDocuments.data ?? []).length - 1
                  }
                  onPrevious={() =>
                    router.push(
                      `/project-sales/${projectId}/quotation-documents/${
                        (siblingDocuments.data ?? [])[documentIndex - 1].id
                      }`,
                    )
                  }
                  onNext={() =>
                    router.push(
                      `/project-sales/${projectId}/quotation-documents/${
                        (siblingDocuments.data ?? [])[documentIndex + 1].id
                      }`,
                    )
                  }
                  ariaLabel="quotation"
                />
              )
            }
            gear={
              <DetailActionsMenu ariaLabel="Quotation actions">
                {/* Edit's ENTRY POINT lives here, not in the header: one primary CTA, everything
                    else behind the gear. Only the way IN moved - once a session is open, Cancel
                    and Save are the header's controls and they stay on screen. */}
                {canEdit && !edit.isEditing && (
                  <DropdownMenuItem onSelect={startEditing}>
                    <SquarePen className="size-4" aria-hidden />
                    Edit quotation
                  </DropdownMenuItem>
                )}
                {canEdit && (
                  <DropdownMenuItem onSelect={() => setSigning(true)}>
                    <PenLine className="size-4" aria-hidden />
                    {isSigned ? 'Sign again' : 'Sign quotation'}
                  </DropdownMenuItem>
                )}
                {/* Disabled rather than absent: the client asked for both exports, and a menu that
                    simply lacks them reads as "this system cannot do it". The subtext names where
                    the file lands, because the click itself no longer produces one. */}
                <DropdownMenuItem
                  disabled={!record.is_issued || mutations.issuePdf.isPending}
                  onSelect={() => void queueIssuePdf()}
                >
                  <Download className="size-4" aria-hidden />
                  <span className="min-w-0">
                    Download PDF
                    <span className="block text-xs text-muted-foreground">
                      {record.is_issued ? 'Prepared in My Downloads' : 'Issue it first'}
                    </span>
                  </span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={!record.is_issued || mutations.issueXlsx.isPending}
                  onSelect={() => void queueIssueXlsx()}
                >
                  <Download className="size-4" aria-hidden />
                  <span className="min-w-0">
                    Download Excel
                    <span className="block text-xs text-muted-foreground">
                      {record.is_issued ? 'Prepared in My Downloads' : 'Issue it first'}
                    </span>
                  </span>
                </DropdownMenuItem>
                {canEdit && (
                  <DropdownMenuItem
                    disabled={!record.is_issued || mutations.signLink.isPending}
                    onSelect={(event) => {
                      event.preventDefault();
                      void copyCounterSignLink();
                    }}
                  >
                    {signLinkCopied ? (
                      <Check className="size-4" aria-hidden />
                    ) : (
                      <Link2 className="size-4" aria-hidden />
                    )}
                    <span className="min-w-0">
                      {signLinkCopied ? 'Copied' : 'Copy counter-sign link'}
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
            }
            primary={
              <>
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
                    {isSaving ? 'Saving...' : 'Save quotation'}
                  </Button>
                </>
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
                  disabled={mutations.issue.isPending || !isSigned || needsApproval}
                  title={
                    needsApproval
                      ? 'A manager has to approve the below-floor pricing first'
                      : isSigned
                        ? undefined
                        : 'Sign it first'
                  }
                  onClick={() => mutations.issue.mutate(documentId)}
                >
                  {`Issue R${nextIssueNo}`}
                </Button>
              )}
              {/* Where a queued export is actually collected. Rendered only once something has
                  been issued, because a download of a revision that does not exist yet cannot: the
                  gear already says "Issue it first", and a chip that can only ever read 0 is a
                  control with nothing behind it.

                  Keyed to the LATEST revision, which is the one whose exports anybody is chasing.
                  Earlier revisions' files are still in the My Downloads drawer. */}
              {latestIssue && (
                <EntityDownloadsButton
                  entityType="quotation_issue"
                  entityId={latestIssue.id}
                  label={latestIssue.our_ref_text ?? `${record.document_no} R${latestIssue.issue_no}`}
                  // The complaint header's own three classes, verbatim. It was always the same
                  // component; passing no className rendered it borderless beside two bordered
                  // buttons, which is why the client read it as not clickable ("the download
                  // should have border just like complaint").
                  className="h-8 border border-border"
                />
              )}
              </>
            }
          />
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

      {/* What the CUSTOMER said, on the document rather than behind the Signatures tab. Renders
          nothing unless they have actually asked for something, and stands down the moment they
          sign - acceptance wins here exactly as it does on their own counter-sign page.

          Above the price-floor gate on purpose: this is somebody waiting on an answer, the gate
          below is a rule about what may be sent. */}
      <QuotationChangesRequestedPanel
        document={record}
        reviseLabel={reviseLabel}
        // The SAME entry point Edit uses, so a revision is still something the salesperson is
        // asked about. Withheld from a reader, and while a session is already open.
        onRevise={canEdit && !edit.isEditing ? startEditing : undefined}
        isRevising={quotationMutations.revise.isPending}
      />

      {/* The price-floor gate. Renders nothing at all unless a line on this quotation is
          priced below its floor, so the ordinary quotation gains no chrome and no extra step. */}
      <QuotationApprovalPanel
        document={record}
        graph={approvalGraph.data}
        canEdit={canEdit}
        isMoving={mutations.submitForApproval.isPending}
        isDeciding={mutations.approve.isPending || mutations.reject.isPending}
        onMove={(toStatusId) =>
          mutations.submitForApproval.mutate({ id: documentId, toStatusId })
        }
        onApprove={() => mutations.approve.mutate(documentId)}
        onReject={async (reason) => {
          try {
            await mutations.reject.mutateAsync({ id: documentId, reason });
          } catch {
            // The mutation toasted the reason; the dialog closes either way so the manager
            // is not left staring at a form they have already read the failure for.
          }
        }}
      />

      <QuotationDocumentHeader
        document={shown}
        liveGrandTotal={liveGrandTotal}
        onChange={isHeaderEditable ? edit.stageDocument : undefined}
      />

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
        nextVersionLabel={nextVersionLabel}
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
