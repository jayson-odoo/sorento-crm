'use client';

import { APPEAL_VERB } from '@/lib/submission-status';
import * as React from 'react';
import Link from 'next/link';
import { TruncatedTextCell } from '@/components/common/TruncatedTextCell';
import { usePathname, useRouter } from 'next/navigation';
import { ChevronDown, GitBranch, Mail, MessageCircle, PenLine, RefreshCw } from 'lucide-react';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { RecordHeaderCard } from '@/components/common/RecordHeaderCard';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { RecordAction } from '@/components/common/recordActions';
import DetailActions from '@/components/common/DetailActions';
import { EntityDownloadsButton } from '@/components/my-downloads/EntityDownloadsButton';
import {
  useQuotationFeedback,
  useQuotationApprovalGraph,
  useQuotationDocument,
  useQuotationDocumentMutations,
  useQuotationDocuments,
  useQuotationIssues,
} from '../../../../_shared/hooks/useQuotationDocuments';
import RecordNavigation from '@/components/common/RecordNavigation';
import {
  useFindScopeWithLine,
  useProject,
  useProjectQuotationVersions,
  useQuotationMutations,
  useQuotationRecomputeMutation,
  useQuotations,
} from '../../../../_shared/hooks/useProjects';
import type { QuotationRecomputeResult } from '../../../../_shared/types/project.types';
import { ReviseQuotationDialog } from '../../../components/ReviseQuotationDialog';
import {
  isLockedForApproval,
  nextAction,
  quotationStanding,
} from '../../../../_shared/lib/quotationDecision';
import { useQuotationDocumentActions } from '../../actions';
import {
  APPROVE_PERMISSION,
  QuotationApprovalPanel,
  type ApprovalLineFlag,
} from './QuotationApprovalPanel';
import { LINE_FLAG_FILTERS } from '../../../components/QuotationVersionEditor';
import { storedLineFacts } from '../../../components/QuotationLineFlags';
import { QuotationRejectDialog } from './QuotationRejectDialog';
import { ReviseApprovalDialog } from './ReviseApprovalDialog';
import { QuotationChangesRequestedPanel } from './QuotationChangesRequestedPanel';
import { QuotationViewCount } from './QuotationViewCount';
import { QuotationDocumentProvider } from './QuotationDocumentContext';
import { QuotationDocumentTabs, quotationSiblingHref } from './QuotationDocumentTabs';
import { ReviseToEditDialog } from './ReviseToEditDialog';
import { documentNoun } from '../../../../_shared/services/quotationDocumentService';

/**
 * One quotation DOCUMENT: the letterhead the customer receives, and the tabs it is read through.
 *
 * This is the shell every tab renders inside. The identity of the record - its status, the project
 * title and developer lines, the one CTA and the gear - sits ABOVE the tabs and stays on screen
 * wherever the reader goes. The letterhead card (refs, recipient, total) is the Header tab (#1341).
 *
 * The header follows the system's own rule and nothing else: ONE primary CTA, and every other
 * action behind the gear. Download is not a call to action, it is a thing you can also do;
 * issuing is the move that changes what the customer holds. Edit quotation is behind the gear for
 * the same reason, and opens the whole quotation in the form page (#1341): this page is a read.
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
  const pathname = usePathname();
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
   * Read here rather than inside the Lines tab because Edit sits in this header and is on
   * screen from every tab. Both queries are the ones the Lines tab and the line editor already
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
  // Edit quotation opens the form page (#1341): "Edit quotation means I edit the whole quotation".
  const editPath = `/project-sales/${projectId}/quotation-documents/${documentId}/edit`;

  const [activeScopeId, setActiveScopeId] = React.useState<string | null>(null);
  const [revisePrompt, setRevisePrompt] = React.useState(false);
  const [approvalRevisePrompt, setApprovalRevisePrompt] = React.useState(false);
  const [rejecting, setRejecting] = React.useState(false);
  const canApprove = useHasPermission(APPROVE_PERMISSION);
  /**
   * The version the header chip shows (PROPOSAL-HEADER-LAYOUT, owner: "should just be v1,
   * version is per quotation / proposal"). Null is the current one. Versions are stored per
   * area, so the number picked here is applied to every area below.
   */
  const [versionNo, setVersionNo] = React.useState<number | null>(null);
  const [revisingAll, setRevisingAll] = React.useState(false);
  const [recheckResults, setRecheckResults] = React.useState<
    Record<string, QuotationRecomputeResult>
  >({});
  const recompute = useQuotationRecomputeMutation(projectId);
  const dismissRecheck = React.useCallback(
    (versionId: string) =>
      setRecheckResults((prev) => {
        const next = { ...prev };
        delete next[versionId];
        return next;
      }),
    [],
  );

  const selectScope = React.useCallback((scopeId: string) => setActiveScopeId(scopeId), []);

  // The lines filter (PROJECT-QUOTE-LINE-TOOLS): on across area tabs, and set by the banner.
  const [lineFlags, setLineFlags] = React.useState<string[]>([]);
  const [linesScrollRequest, setLinesScrollRequest] = React.useState(0);
  const linesScrollPending = React.useRef(false);
  const consumeLinesScroll = React.useCallback(() => {
    const pending = linesScrollPending.current;
    linesScrollPending.current = false;
    return pending;
  }, []);
  const findScopeWithLine = useFindScopeWithLine();
  /**
   * A banner count, pressed: the lines filtered to what it counts, on the first area holding one,
   * on the Header tab where the lines are. Judged by the STORED flags, which are what it counts.
   */
  const showFlaggedLines = React.useCallback(
    async (flag: ApprovalLineFlag) => {
      setLineFlags([flag]);
      // The banner counts the CURRENT versions, so the lines shown are the current ones too.
      setVersionNo(null);
      const header = `/project-sales/${projectId}/quotation-documents/${documentId}`;
      if (pathname !== header) router.push(header);
      const option = LINE_FLAG_FILTERS.find((row) => row.value === flag);
      const scopes = [...(document.data?.scopes ?? [])].sort((a, b) => a.sort_order - b.sort_order);
      if (!option) return;
      try {
        const scopeId = await findScopeWithLine(
          scopes.map((scope) => ({ scopeId: scope.id, versionId: scope.current_version_id })),
          (line) => option.test(storedLineFacts(line)),
        );
        if (scopeId) setActiveScopeId(scopeId);
      } catch {
        // The filter is on all the same; the open area stays as it was.
      }
      // Bring the lines into view, after the area switch, whether or not one was found.
      linesScrollPending.current = true;
      setLinesScrollRequest((n) => n + 1);
    },
    [document.data?.scopes, documentId, findScopeWithLine, pathname, projectId, router],
  );

  // Memoised because the total below is: `?? []` mints a new array whenever the document has no
  // scopes, which would re-sum the header on every render of the page.
  const documentScopes = document.data?.scopes;
  const scopes = React.useMemo(() => documentScopes ?? [], [documentScopes]);

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

  /** Every area of THIS document with its current version, for the gear's Recheck and Revise. */
  const currentScopes = React.useMemo(() => {
    const mine = new Set(scopes.map((scope) => scope.id));
    return (quotations.data ?? [])
      .filter((quotation) => mine.has(quotation.id))
      .map((quotation) => ({
        quotation,
        current: scopeVersions.rows.find(
          (row) => row.quotation.id === quotation.id && row.version.is_current,
        )?.version,
      }))
      .flatMap((pair) => (pair.current ? [{ quotation: pair.quotation, current: pair.current }] : []));
  }, [quotations.data, scopeVersions.rows, scopes]);
  /** The proposal's version numbers, newest first, across its areas. */
  const documentVersionNos = React.useMemo(() => {
    const mine = new Set(scopes.map((scope) => scope.id));
    const numbers = new Set(
      scopeVersions.rows
        .filter((row) => mine.has(row.quotation.id))
        .map((row) => row.version.version_no),
    );
    return [...numbers].sort((a, b) => b - a);
  }, [scopeVersions.rows, scopes]);
  const currentVersionNo = currentScopes.length
    ? Math.max(...currentScopes.map((pair) => pair.current.version_no))
    : null;
  // A number some area still holds as its CURRENT version is not frozen, even when another area
  // has moved past it (an area added later starts lower).
  const currentNumbers = new Set(currentScopes.map((pair) => pair.current.version_no));
  const allSameVersion = currentNumbers.size <= 1;

  const canEditProject = project.data?.can_edit ?? false;
  // The customer's feedback notes (PS-QUOTE-MATRIX): the open count is the tab's badge. The same
  // query as the Customer feedback tab and the Lines grid's marks.
  const feedback = useQuotationFeedback(projectId, documentId);
  const gear = useQuotationDocumentActions({
    projectId,
    document: document.data,
    canEdit: canEditProject,
    latestIssue: issues.data?.[0] ?? null,
    onEdit: startEditing,
    onDeleted: () => router.push(`/project-sales/${projectId}?tab=quotations`),
    surface: 'inline',
    projectOutcome: project.data?.outcome ?? null,
    projectHasQuotation: (siblingDocuments.data ?? []).some((row) => row.kind === 'quotation'),
  });

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
  const standing = quotationStanding(record);
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
  // The grant is the RIGHT to approve; the server says whether THIS viewer may decide THIS
  // request (routed approver, someone above them, or an admin, never the sender). An older
  // payload without the field falls back to the grant.
  const mayDecide =
    record.viewer_may_decide === undefined || record.viewer_may_decide === null
      ? canApprove
      : canApprove && record.viewer_may_decide;
  const action = nextAction(record, { canEdit, canApprove: mayDecide, isSigned });
  const locked = isLockedForApproval(record);

  /**
   * Recheck alerts and Revise to vN, moved up from the row above the lines into the gear
   * (owner, 5 Nov 2026: "the version should be shown at the header tab"). Same rules as the
   * buttons they replace: a user who can edit, a quotation not locked for approval, and for the
   * recheck only versions that are still open. They act on every area, the version being the
   * proposal's.
   */
  const openScopes = currentScopes.filter(
    (pair) => pair.current.is_editable ?? pair.current.is_current,
  );
  const versionActions: RecordAction[] = [];
  if (canEdit && !locked && openScopes.length > 0) {
    versionActions.push({
      key: 'quotation_document.recheck_alerts',
      label: recompute.isPending ? 'Rechecking...' : 'Recheck alerts',
      icon: RefreshCw,
      disabled: recompute.isPending,
      run: async () => {
        setVersionNo(null);
        for (const pair of openScopes) {
          try {
            const result = await recompute.mutateAsync(pair.current.id);
            setRecheckResults((prev) => ({ ...prev, [pair.current.id]: result }));
          } catch {
            // The mutation toasted the reason; the other areas still get their recheck.
          }
        }
      },
    });
  }
  if (canEdit && !locked && currentScopes.length > 0 && currentVersionNo !== null) {
    versionActions.push({
      key: 'quotation_document.revise_version',
      label: allSameVersion ? `Revise to v${currentVersionNo + 1}` : 'Revise every area',
      icon: GitBranch,
      run: () => setRevisingAll(true),
    });
  }
  const gearActions = (() => {
    const at = gear.actions.findIndex((item) => item.key === 'quotation_document.edit');
    if (at < 0) return [...versionActions, ...gear.actions];
    return [...gear.actions.slice(0, at + 1), ...versionActions, ...gear.actions.slice(at + 1)];
  })();
  const shownVersionNo = versionNo ?? currentVersionNo;
  const versionFrozen = versionNo !== null && !currentNumbers.has(versionNo);
  const versionLabel =
    shownVersionNo === null ? null : `v${shownVersionNo}${versionFrozen ? ' (frozen)' : ''}`;
  /**
   * The "Send for approval" label comes off the graph's own draft -> pending edge, so a renamed
   * edge reads the way the admin named it; with no graph it falls back to the plain words. The
   * target is the pending rung itself: the server walks Rejected -> Draft -> Pending on its own.
   */
  const pendingStatus = approvalGraph.data?.statuses.find((row) => row.key === 'pending_approval');
  const draftStatus = approvalGraph.data?.statuses.find((row) => row.key === 'draft');
  // From Rejected the same press is a resubmission (RESUBMITTED-STATUS): the server lands it on
  // the resubmitted rung, so the label comes off that rung's draft -> resubmitted edge.
  const isResubmit = record.approval_status_key === 'rejected';
  const resubmittedStatus = approvalGraph.data?.statuses.find((row) => row.key === 'resubmitted');
  const sendTarget = isResubmit && resubmittedStatus ? resubmittedStatus : pendingStatus;
  const sendEdge = approvalGraph.data?.transitions.find(
    (edge) => edge.to_status_id === sendTarget?.id && edge.from_status_id === draftStatus?.id,
  );
  const sendForApprovalLabel =
    sendEdge?.label || (isResubmit ? APPEAL_VERB : 'Send for approval');

  /** What the next copy of a single frozen scope will be called, e.g. "v3". */
  const nextVersionLabel =
    lockedScopes.length === 1 && lockedScopes[0].current
      ? `v${lockedScopes[0].current.version_no + 1}`
      : null;
  /**
   * What pressing the change-request banner's button will actually do, said in its label.
   *
   * Deliberately NOT "Revise to v3": the gear already carries an item by that exact name (a
   * plain revise, no form), and two controls reading the same words is worse than a vaguer
   * label. This one leads into editing, and the prompt it opens names the scopes and the version
   * it will mint.
   *
   * With no frozen scope left (a revision is already open) the click goes straight to the
   * form page, and the label has to say that rather than promise a version it will not mint.
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
  // No "The customer holds this version. Edit opens the next one." (owner, 5 Nov 2026): Edit's
  // own prompt (ReviseToEditDialog) says it when it matters.
  const headerHints: string[] = [];
  if (!canEdit) headerHints.push('You can read this quotation but not change it.');
  if (action.hint) headerHints.push(action.hint);

  /**
   * Edit quotation: the whole quotation in the form page (#1341). On a quotation the customer
   * holds it asks first, because the answer is a revision; the form opens once that is made.
   */
  function startEditing() {
    if (locked) {
      setApprovalRevisePrompt(true);
      return;
    }
    if (lockedScopes.length > 0) {
      setRevisePrompt(true);
      return;
    }
    router.push(editPath);
  }

  async function reviseApprovalThenEdit(reason: string) {
    try {
      await mutations.reviseApproval.mutateAsync({ id: documentId, reason });
      setApprovalRevisePrompt(false);
      router.push(editPath);
    } catch {
      // The mutation toasted the reason. The dialog stays open so it can be tried again.
    }
  }

  async function reviseThenEdit() {
    try {
      // Sequentially, not in parallel: each revise reads and freezes the scope's current
      // version, and the failure of one must not leave the rest half-opened behind a spinner.
      for (const pair of lockedScopes) {
        await quotationMutations.revise.mutateAsync(pair.quotation.id);
      }
      setRevisePrompt(false);
      router.push(editPath);
    } catch {
      // The mutation toasted the reason. The dialog stays open so it can be tried again.
    }
  }

  return (
    <div className="space-y-5">
      {/* The Order Inquiry record card (PROPOSAL-HEADER-LAYOUT, owner 5 Nov 2026: "it should be
          like order inquiry"): number + status inline, muted lines under it, actions right. No
          customer line (the letterhead's To says it) and nothing hangs under the buttons. */}
      <RecordHeaderCard
        title={record.document_no}
        badges={
          <>
            {/* The SAME reading as the project's quotation list (`quotationStanding`), so the two
                surfaces never answer the same question differently. */}
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(standing.label)}`}>
              {standing.label}
            </span>
            {versionLabel &&
              (documentVersionNos.length > 1 ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-6 px-2 text-xs"
                      aria-label={`Version ${versionLabel}`}
                    >
                      {versionLabel}
                      <ChevronDown className="size-3.5" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    {documentVersionNos.map((no) => (
                      <DropdownMenuItem
                        key={no}
                        onSelect={() => setVersionNo(no === currentVersionNo ? null : no)}
                      >
                        {no === currentVersionNo
                          ? `v${no} (current)`
                          : currentNumbers.has(no)
                            ? `v${no}`
                            : `v${no} (frozen)`}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <span className="inline-flex h-6 items-center rounded-md border border-border px-2 text-xs font-medium">
                  {versionLabel}
                </span>
              ))}
          </>
        }
        subtitle={[
          <TruncatedTextCell
            key="title"
            text={record.subject_title}
            lines={2}
            dialogTitle="Title"
          />,
          record.is_issued ? (
            <QuotationViewCount key="views" projectId={projectId} document={record} />
          ) : null,
          // Why the screen is in the state it is in, each on its own line (owner: no "·").
          // Visible, not a tooltip: a hover is unreadable on the phone this page works on.
          ...headerHints.map((hint) => <span key={hint}>{hint}</span>),
          // QUOTE-AUTOSAVE: the form autosaves into a draft that reaches this record only on
          // Save, so say when one is waiting, and whose.
          record.has_form_draft ? (
            <span key="form-draft" className="inline-flex flex-wrap items-center gap-x-1">
              {formDraftHint(record.form_draft_at, record.form_draft_by_name)}
              <Button
                type="button"
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={startEditing}
              >
                Continue editing
              </Button>
            </span>
          ) : null,
        ]}
        actions={
          /* Pager, gear, printer, primary (D6, owner 5 Nov: the printer sits beside the gear). */
          <DetailActions
            pagerNode={
              /* Step between this project's quotation documents without going back to the
                  list, the users-detail pattern. List mode off the cached documents query -
                  the list screen the user came from already fetched it, so the neighbours
                  cost nothing. Rendered from two documents up, since with one there is nowhere to go. */
              (siblingDocuments.data ?? []).length > 1 && (
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
                      quotationSiblingHref(
                        projectId,
                        documentId,
                        (siblingDocuments.data ?? [])[documentIndex - 1].id,
                        pathname,
                      ),
                    )
                  }
                  onNext={() =>
                    router.push(
                      quotationSiblingHref(
                        projectId,
                        documentId,
                        (siblingDocuments.data ?? [])[documentIndex + 1].id,
                        pathname,
                      ),
                    )
                  }
                  ariaLabel="quotation"
                />
              )
            }
            pendingAction={gear.pending}
            gear={
              <>
                <DetailActionsMenu
                  actions={gearActions}
                  ariaLabel={`${documentNoun(document.data)} actions`}
                />
                {/* Where a queued export is actually collected. Rendered only once something has
                    been issued, because a download of a revision that does not exist yet cannot: the
                    gear already says "Send it to the customer first", and a chip that can only ever read 0 is a
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
            primary={
              <>
              {action.kind === 'sign' && (
                <Button type="button" size="sm" onClick={gear.openSign}>
                  <PenLine className="size-4" aria-hidden />
                  Sign
                </Button>
              )}
              {action.kind === 'send_for_approval' && (
                <Button
                  type="button"
                  size="sm"
                  disabled={mutations.submitForApproval.isPending}
                  onClick={() => {
                    if (!pendingStatus) {
                      toast.error('The approval steps are still loading. Try again in a moment.');
                      return;
                    }
                    mutations.submitForApproval.mutate({
                      id: documentId,
                      toStatusId: pendingStatus.id,
                    });
                  }}
                >
                  {sendForApprovalLabel}
                </Button>
              )}
              {action.kind === 'approve' && (
                <>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={mutations.reject.isPending}
                    onClick={() => setRejecting(true)}
                  >
                    Reject
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={mutations.approve.isPending}
                    onClick={() => mutations.approve.mutate(documentId)}
                  >
                    Approve
                  </Button>
                </>
              )}
              {action.kind === 'send' && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button type="button" size="sm" disabled={mutations.issue.isPending}>
                      {/* The owner on "Issue R1": "call this Send to Customer" (#1341). The revision
                          stays in the label, as it did, because R2 is a different paper from R1. The
                          API and the status names keep "issue". */}
                      {`Send to Customer ${record.next_revision_label ?? `R${nextIssueNo}`}`}
                      <ChevronDown className="size-4" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onSelect={() => mutations.issue.mutate(documentId)}>
                      <Mail className="size-4" aria-hidden />
                      Email
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() =>
                        mutations.issue.mutate(documentId, {
                          onSuccess: (issue) => gear.openWhatsApp(issue),
                        })
                      }
                    >
                      <MessageCircle className="size-4" aria-hidden />
                      WhatsApp
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              </>
            }
          />
        }
      />

      {/* What the CUSTOMER said, on the document rather than behind the Signatures tab. Renders
          nothing unless they have actually asked for something, and stands down the moment they
          sign - acceptance wins here exactly as it does on their own counter-sign page.

          Above the price-floor gate on purpose: this is somebody waiting on an answer, the gate
          below is a rule about what may be sent. */}
      <QuotationChangesRequestedPanel
        document={record}
        reviseLabel={reviseLabel}
        // The SAME entry point Edit uses, so a revision is still something the salesperson is
        // asked about. Withheld from a reader.
        onRevise={canEdit ? startEditing : undefined}
        isRevising={quotationMutations.revise.isPending}
      />

      {/* The price-floor gate. Renders nothing at all unless a line on this quotation is
          priced below its floor, so the ordinary quotation gains no chrome and no extra step. */}
      <QuotationApprovalPanel document={record} onShowLines={showFlaggedLines} />

      {/* The letterhead card and, under it, the lines are the Header tab (#1341; lines moved there
          by PROPOSAL-HEADER-LAYOUT, 5 Nov 2026). */}
      <QuotationDocumentTabs
        projectId={projectId}
        documentId={documentId}
        openFeedback={feedback.data?.open_count ?? 0}
      />

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
          lineFlags,
          setLineFlags,
          linesScrollRequest,
          consumeLinesScroll,
          versionNo,
          recheckResults,
          dismissRecheck,
        }}
      >
        {children}
      </QuotationDocumentProvider>

      {gear.dialogs}

      <ReviseToEditDialog
        open={revisePrompt}
        onOpenChange={setRevisePrompt}
        scopeLabels={lockedScopes.map((pair) => pair.quotation.scope_label)}
        nextVersionLabel={nextVersionLabel}
        isRevising={quotationMutations.revise.isPending}
        onConfirm={reviseThenEdit}
      />

      {revisingAll && (
        <ReviseQuotationDialog
          projectId={projectId}
          scopes={currentScopes.map((pair) => ({
            quotation: pair.quotation,
            currentVersionNo: pair.current.version_no,
            lineCount: pair.quotation.line_count ?? 0,
          }))}
          onDone={() => {
            setRevisingAll(false);
            // Land on the version just opened, not on one picked a moment ago.
            setVersionNo(null);
          }}
        />
      )}

      <ReviseApprovalDialog
        open={approvalRevisePrompt}
        onOpenChange={setApprovalRevisePrompt}
        isRevising={mutations.reviseApproval.isPending}
        onConfirm={reviseApprovalThenEdit}
      />

      <QuotationRejectDialog
        open={rejecting}
        onOpenChange={setRejecting}
        isDeciding={mutations.reject.isPending}
        onReject={(reason) => mutations.reject.mutateAsync({ id: documentId, reason })}
      />
    </div>
  );
}

/** "Unsaved draft, last edited 10/11/2026 2:14 PM by Aina" (QUOTE-AUTOSAVE). */
export function formDraftHint(at: string | null | undefined, by: string | null | undefined): string {
  const when = at ? ` ${formatDateTimeInMalaysia(at)}` : '';
  return `Unsaved draft, last edited${when}${by ? ` by ${by}` : ''}.`;
}
