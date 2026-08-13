'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import {
  AlertCircle,
  Ban,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  Search,
  TrendingUp,
  UserRoundCog,
  UserRoundPlus,
  X,
} from 'lucide-react';

import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia, parseDateTimeAsUTC } from '@/lib/helpers';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const PAGE_SIZE = 5;
const MAX_TIER = 3;
import {
  getMyPendingSLA,
  getTeamPendingSLA,
  getTakeoverState,
  resolveConversationSLATracking,
  escalateConversationSLATracking,
  type MyPendingSLAItem,
  type TeamPendingItem,
  type TakeoverInfo,
  type TakeoverStateRow,
} from '../services/conversationSLATrackingService';
import {
  useCancelTakeover,
  useReassignSLATracking,
  useRejectTakeover,
  useTakeoverSLATracking,
} from '../hooks/useTeamPendingSLA';
import type { InterventionTicketListItem } from '../services/interventionTicketService';
import ReassignDialog from './ReassignDialog';
import { TakeoverCountdown } from './TakeoverCountdown';
import ExtendDueButton from './ExtendDueButton';
import InterventionTicketDrawer from './InterventionTicketDrawer';
import TicketSlaChips from './TicketSlaChips';
import { CoverageManager } from '@/app/(protected)/account/notifications/components';

// Same inbox base used by the SLA detail page; conversation rows deep-link here
// because the CRM cannot send files in-app yet — staff reply from Respond.
const RESPOND_IO_INBOX_BASE_URL = 'https://app.respond.io/space/364817/inbox';

const ENTITY_ROUTES: Record<string, { base: string; label: string }> = {
  stock_inquiry: { base: '/procurement-management/stock-inquiries', label: 'Stock inquiry' },
  complaint: { base: '/complaint-management/complaints', label: 'Complaint' },
  purchase_request: { base: '/procurement-management/purchase-requests', label: 'Purchase request' },
  sponsorship_form: { base: '/procurement-management/purchase-requests', label: 'Sponsorship form' },
};

type AnyTask = MyPendingSLAItem | TeamPendingItem;

/** Form-vs-conversation is decided by the backend (is_form_sla, from FORM_SLA_TYPES)
 * — never re-derived here, or types the FE route map doesn't know (e.g. 'ticket')
 * silently fall through to the conversation branch. */
function isFormTask(item: AnyTask): boolean {
  return item.is_form_sla;
}

/** Intervention-ticket rows are flagged by the backend (`is_intervention_ticket`),
 * never re-derived - a pre-migration conversation row keeps its old behaviour of
 * opening the Respond inbox. */
function asTicket(item: AnyTask): InterventionTicketListItem | null {
  return (item as InterventionTicketListItem).is_intervention_ticket
    ? (item as InterventionTicketListItem)
    : null;
}

/** The pending takeover on a row, if any (null otherwise). */
function pendingTakeover(item: AnyTask): TakeoverInfo | null {
  const tk = item.takeover;
  return tk && tk.status === 'pending' ? tk : null;
}

/** In-system record link when we have a known route for the form type; null when we
 * don't (e.g. ticket — the row falls back to its Respond conversation / SLA detail). */
function entityHref(item: AnyTask): string | null {
  const route = ENTITY_ROUTES[item.source_entity_type ?? ''];
  if (route && item.source_entity_id) return `${route.base}/${item.source_entity_id}`;
  return null;
}

function humanizeType(item: AnyTask): string {
  const route = ENTITY_ROUTES[item.source_entity_type ?? ''];
  if (route) return route.label;
  if (item.is_form_sla && item.source_entity_type) {
    return item.source_entity_type
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return 'Enquiry';
}

function respondId(item: AnyTask): string | null {
  return (item as MyPendingSLAItem).respond_io_id ?? null;
}

function dueLabel(due: string | null): { text: string; overdue: boolean } {
  if (!due) return { text: 'No due date', overdue: false };
  // Backend emits naive-UTC deadlines; parse as UTC and render in Malaysia wall-clock.
  const d = parseDateTimeAsUTC(due);
  const overdue = d.getTime() < Date.now();
  return { text: formatDateTimeInMalaysia(due), overdue };
}

/** Free-text haystack for the search box: entity number (reference) for form rows,
 * contact name (reference) for conversation rows, plus type + assignee/team. */
function matchesQuery(item: AnyTask, typeLabel: string, q: string): boolean {
  if (!q) return true;
  const t = item as TeamPendingItem;
  const ticket = asTicket(item);
  const hay = [
    typeLabel,
    item.reference ?? '',
    t.assignee_name ?? '',
    t.team_label ?? '',
    item.source_entity_type ?? '',
    ticket?.contact_name ?? '',
    ticket?.enquiry_snippet ?? '',
  ]
    .join(' ')
    .toLowerCase();
  return hay.includes(q);
}

type Mode = 'mine' | 'team' | 'coverage';

const SLA_PERM = 'sla_management.conversation_sla_tracking';

export default function MyPendingSLAWidget() {
  const router = useRouter();
  // Per-action RBAC: each task button is independently granted. superadmin/admin
  // hold all. Buttons hide when the slug is absent; the matching routes also 403.
  const canExtend = useHasPermission(`${SLA_PERM}.extend`);
  const canReassign = useHasPermission(`${SLA_PERM}.reassign`);
  const canResolve = useHasPermission(`${SLA_PERM}.resolve`);
  const canEscalate = useHasPermission(`${SLA_PERM}.escalate`);
  const canTakeover = useHasPermission(`${SLA_PERM}.takeover`);
  const canManageTeamCoverage = useHasPermission('notifications.coverage.manage_team');
  const [mode, setMode] = useState<Mode>('mine');
  const [items, setItems] = useState<MyPendingSLAItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [teamItems, setTeamItems] = useState<TeamPendingItem[] | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [resolveTarget, setResolveTarget] = useState<MyPendingSLAItem | null>(null);
  const [resolving, setResolving] = useState(false);
  const [escalateTarget, setEscalateTarget] = useState<MyPendingSLAItem | null>(null);
  const [escalateReason, setEscalateReason] = useState('');
  const [escalating, setEscalating] = useState(false);
  const [reassignTarget, setReassignTarget] = useState<{ id: string; label: string } | null>(null);
  const [takeoverTarget, setTakeoverTarget] = useState<TeamPendingItem | null>(null);
  // Intervention tickets: own enquiry per row, answered in an in-place drawer.
  // Ticket rows arrive already merged into `/my-pending` (flagged
  // `is_intervention_ticket`), so there is no separate ticket list to load here.
  const [openTicketId, setOpenTicketId] = useState<string | null>(null);

  const takeoverMutation = useTakeoverSLATracking();
  const reassignMutation = useReassignSLATracking();
  const cancelMutation = useCancelTakeover();
  const rejectMutation = useRejectTakeover();

  // Contested-task banner driven by the email deep link ?takeover=<tracking_id>.
  const searchParams = useSearchParams();
  const takeoverParam = searchParams.get('takeover');
  // Coverage deep link ?team_task=<tracking_id>: open My Team + highlight the row so the
  // coverer can take it over (the colleague's task surfaces in My Team).
  const teamTaskParam = searchParams.get('team_task');
  // Ticket assignment-notify deep link ?ticket=<tracking_id> (UAC AC-G1): open the
  // drawer directly, no navigation, no page to land on first.
  const ticketParam = searchParams.get('ticket');
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [banner, setBanner] = useState<TakeoverStateRow | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);

  const load = useCallback(() => {
    return getMyPendingSLA()
      .then((data) => setItems(data))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  const loadTeam = useCallback(() => {
    return getTeamPendingSLA({ limit: 50 })
      .then((res) => setTeamItems(res.data))
      .catch((e) => setTeamError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  useEffect(() => {
    let active = true;
    getMyPendingSLA()
      .then((data) => active && setItems(data))
      .catch((e) => active && setError(e instanceof Error ? e.message : 'Failed to load'));
    return () => {
      active = false;
    };
  }, []);

  // Team list is loaded lazily the first time the user switches to "My Team".
  useEffect(() => {
    if (mode !== 'team' || teamItems !== null || teamError !== null) return;
    let active = true;
    getTeamPendingSLA({ limit: 50 })
      .then((res) => active && setTeamItems(res.data))
      .catch((e) => active && setTeamError(e instanceof Error ? e.message : 'Failed to load'));
    return () => {
      active = false;
    };
  }, [mode, teamItems, teamError]);

  // Reset paging when switching modes or searching.
  useEffect(() => {
    setPage(0);
  }, [mode, search]);

  // Deep-link banner: pin-fetch the contested task by id (pagination-proof). Switch to
  // My Pending so the owner sees their own row context too.
  useEffect(() => {
    if (!takeoverParam || bannerDismissed) {
      setBanner(null);
      return;
    }
    let active = true;
    setMode('mine');
    getTakeoverState(takeoverParam)
      .then((row) => active && setBanner(row))
      .catch(() => active && setBanner(null));
    return () => {
      active = false;
    };
  }, [takeoverParam, bannerDismissed]);

  // Coverage deep link: open My Team and highlight the target row. The highlight
  // auto-clears after a few seconds; the row's existing Takeover button does the rest.
  useEffect(() => {
    if (!teamTaskParam) return;
    setMode('team');
    setPage(0); // pinned task sits on the first page's first row
    setHighlightId(teamTaskParam);
    const t = setTimeout(() => setHighlightId(null), 6000);
    return () => clearTimeout(t);
  }, [teamTaskParam]);

  // Ticket assignment-notify deep link ?ticket=<tracking_id> (UAC AC-G1): open the
  // drawer directly (no navigation, no row lookup needed - the drawer fetches its
  // own detail by id) and strip the param once consumed so a later refresh doesn't
  // reopen it.
  useEffect(() => {
    if (!ticketParam) return;
    setMode('mine');
    setOpenTicketId(ticketParam);
    router.replace('/', { scroll: false });
  }, [ticketParam, router]);

  // Ticket rows arrive already flagged on `/my-pending` - no separate ticket fetch
  // or merge (Phase 1's mock-only merge was removed in S2.7).
  const mineItems = items;

  // Light polling while any pending takeover is on screen (bar / banner transitions).
  const hasPending = useMemo(() => {
    const a = (items ?? []).some((it) => pendingTakeover(it));
    const b = (teamItems ?? []).some((it) => pendingTakeover(it));
    const c = banner?.takeover?.status === 'pending';
    return a || b || c;
  }, [items, teamItems, banner]);

  useEffect(() => {
    if (!hasPending) return;
    const t = setInterval(() => {
      void load();
      if (mode === 'team' || teamItems !== null) void loadTeam();
      if (takeoverParam && !bannerDismissed) {
        getTakeoverState(takeoverParam).then(setBanner).catch(() => {});
      }
    }, 5000);
    return () => clearInterval(t);
  }, [hasPending, mode, teamItems, takeoverParam, bannerDismissed, load, loadTeam]);

  const clearTakeoverParam = useCallback(() => {
    setBannerDismissed(true);
    setBanner(null);
    if (takeoverParam) router.replace('/', { scroll: false });
  }, [router, takeoverParam]);

  const handleCancelTakeover = (requestId: string) => {
    cancelMutation.mutate(requestId, {
      onSuccess: () => void Promise.all([loadTeam(), load()]),
    });
  };

  const handleRejectTakeover = (requestId: string, fromBanner = false) => {
    rejectMutation.mutate(requestId, {
      onSuccess: () => {
        if (fromBanner) clearTakeoverParam();
        void Promise.all([load(), loadTeam()]);
      },
    });
  };

  const confirmTakeover = () => {
    if (!takeoverTarget) return;
    const t = takeoverTarget;
    takeoverMutation.mutate(
      { id: t.id, teamId: t.team_id },
      {
        onSuccess: () => {
          setTakeoverTarget(null);
          void Promise.all([loadTeam(), load()]);
        },
      },
    );
  };

  const handleReassignConfirm = (userId: string) => {
    if (!reassignTarget) return;
    reassignMutation.mutate(
      { id: reassignTarget.id, userId },
      {
        onSuccess: () => {
          setReassignTarget(null);
          void Promise.all([loadTeam(), load()]);
        },
      },
    );
  };

  // Clicking a row performs its natural action (identical for My Pending and My
  // Team): form rows open the in-system record, conversation rows open the Respond
  // inbox (or the SLA detail when the contact has no resolvable Respond id).
  const openTask = useCallback(
    (item: AnyTask) => {
      // An intervention ticket is answered in place - no navigation, no Respond.
      const ticket = asTicket(item);
      if (ticket) {
        setOpenTicketId(ticket.id);
        return;
      }
      const record = entityHref(item);
      if (record) {
        router.push(record);
        return;
      }
      const rid = respondId(item);
      if (rid) {
        window.open(`${RESPOND_IO_INBOX_BASE_URL}/${rid}`, '_blank', 'noopener,noreferrer');
        return;
      }
      router.push(`/sla-management/conversation-sla-tracking/${item.id}`);
    },
    [router],
  );

  const handleResolve = async () => {
    if (!resolveTarget) return;
    setResolving(true);
    try {
      await resolveConversationSLATracking(resolveTarget.id);
      toast.success('Conversation resolved and closed in Respond.');
      setResolveTarget(null);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to resolve');
    } finally {
      setResolving(false);
    }
  };

  const handleEscalate = async () => {
    if (!escalateTarget) return;
    const reason = escalateReason.trim();
    if (!reason) return;
    setEscalating(true);
    try {
      await escalateConversationSLATracking(escalateTarget.id, reason);
      toast.success('Escalated to the next tier.');
      setEscalateTarget(null);
      setEscalateReason('');
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to escalate');
    } finally {
      setEscalating(false);
    }
  };

  const q = search.trim().toLowerCase();

  const filteredMine = useMemo(
    () => (mineItems ?? []).filter((it) => matchesQuery(it, humanizeType(it), q)),
    [mineItems, q],
  );
  const filteredTeam = useMemo(
    () => (teamItems ?? []).filter((it) => matchesQuery(it, humanizeType(it), q)),
    [teamItems, q],
  );
  // Coverage deep link: pin the targeted task to the FIRST row (pagination-proof) so the
  // coverer sees it immediately and can take it over — mirrors the takeover pin.
  const orderedTeam = useMemo(() => {
    if (!teamTaskParam) return filteredTeam;
    const idx = filteredTeam.findIndex((it) => it.id === teamTaskParam);
    if (idx <= 0) return filteredTeam;
    const copy = filteredTeam.slice();
    const [pinned] = copy.splice(idx, 1);
    return [pinned, ...copy];
  }, [filteredTeam, teamTaskParam]);

  const total = filteredMine.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pageItems = filteredMine.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  const teamTotal = orderedTeam.length;
  const teamPageCount = Math.max(1, Math.ceil(teamTotal / PAGE_SIZE));
  const teamCurrentPage = Math.min(page, teamPageCount - 1);
  const teamPageItems = orderedTeam.slice(
    teamCurrentPage * PAGE_SIZE,
    teamCurrentPage * PAGE_SIZE + PAGE_SIZE,
  );

  const mutatingId =
    (takeoverMutation.isPending && takeoverMutation.variables?.id) ||
    (reassignMutation.isPending && reassignMutation.variables?.id) ||
    null;

  const activeLoaded = mode === 'team' ? teamItems !== null : items !== null;

  // One row renderer for BOTH tabs so the layout never drifts (responsive: title
  // block wraps/truncates, due + chevron stay on the right, actions wrap below).
  const renderRow = (item: AnyTask) => {
    const isTeam = mode === 'team';
    const form = isFormTask(item);
    // Show the deadline this row is racing for its next action (resolution due for
    // resolution-phase rows — the one Extend moves), falling back to the response due.
    const meta = item as MyPendingSLAItem;
    // Show ONLY the active clock the row is racing for its next action (resolution due
    // for resolution-phase rows — the one Extend moves; response due otherwise). One
    // line, labelled by phase. Red already conveys overdue — no extra "overdue" text.
    const due = dueLabel(meta.active_due_at ?? item.due_at);
    const primaryLabel = (meta.due_kind ?? 'respond') === 'resolve'
      ? 'Resolve by'
      : 'Respond by';
    const typeLabel = humanizeType(item);
    const rowBusy = mutatingId === item.id;
    const teamItem = item as TeamPendingItem;
    const mineItem = item as MyPendingSLAItem;
    const tk = pendingTakeover(item);
    const ticket = isTeam ? null : asTicket(item);
    const subline = isTeam
      ? `${teamItem.assignee_name ?? '—'} · ${teamItem.team_label ?? '—'} · Tier ${item.current_tier}`
      : ticket
        ? // AC-E7: a snippet the n8n spine never mapped arrives blank or as
          // whitespace, not null - trim before falling back so the row always
          // says something.
          ticket.enquiry_snippet?.trim() || 'Enquiry from this contact'
        : `Tier ${item.current_tier} · ${form ? mineItem.next_action ?? 'Action required' : 'Reply'}`;
    const atMaxTier = item.current_tier >= MAX_TIER;
    const highlighted = !!highlightId && item.id === highlightId;

    return (
      <li
        key={item.id}
        className="py-1"
        ref={
          highlighted
            ? (el) => el?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
            : undefined
        }
      >
        <div
          tabIndex={0}
          role="button"
          onClick={() => openTask(item)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              openTask(item);
            }
          }}
          className={`-mx-2 cursor-pointer rounded-md px-2 py-2 transition-colors hover:bg-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring${
            highlighted ? ' ring-2 ring-primary bg-primary/5 animate-pulse' : ''
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium" title={`${typeLabel}${item.reference ? ` · ${item.reference}` : ''}`}>
                {typeLabel}
                {item.reference ? (
                  <span className="text-muted-foreground"> · {item.reference}</span>
                ) : null}
              </p>
              <p className="truncate text-xs text-muted-foreground" title={subline}>
                {subline}
              </p>
              {/* A ticket races two clocks at once, so both are shown inline
                  rather than only the active one. */}
              {ticket && (
                <TicketSlaChips
                  className="mt-1.5"
                  dueAt={ticket.due_at}
                  dueAtResolution={ticket.due_at_resolution ?? null}
                  isResponded={ticket.is_responded}
                  respondedAt={ticket.responded_at}
                  currentTier={ticket.current_tier}
                  escalatedAt={ticket.escalated_at}
                />
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {!ticket && (
                <span
                  className={`text-xs ${due.overdue ? 'font-medium text-destructive' : 'text-muted-foreground'}`}
                  title={due.text}
                >
                  {primaryLabel}: {due.text}
                </span>
              )}
              {ticket ? (
                <ChevronRight className="size-4 text-muted-foreground" />
              ) : !entityHref(item) && respondId(item) ? (
                <ExternalLink className="size-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="size-4 text-muted-foreground" />
              )}
            </div>
          </div>

          {/* Inline actions; clicks here must not trigger the row's open action. */}
          <div className="mt-2 flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
            {tk && (
              <div className="rounded-md border border-amber-300/60 bg-amber-50/60 px-2.5 py-2 dark:bg-amber-950/20">
                <div className="mb-1.5 flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                  <Ban className="size-3.5" />
                  <span className="font-medium">
                    {isTeam
                      ? `Takeover pending${tk.can_cancel ? '' : ` · ${tk.initiator_name}`}`
                      : `Being taken over by ${tk.initiator_name}`}
                  </span>
                </div>
                <TakeoverCountdown
                  commitAt={tk.commit_at}
                  windowSeconds={tk.window_seconds}
                  onExpire={() => {
                    void load();
                    void loadTeam();
                  }}
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  {canTakeover && tk.can_cancel && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7"
                      data-testid="takeover-cancel"
                      disabled={cancelMutation.isPending}
                      onClick={() => handleCancelTakeover(tk.request_id)}
                    >
                      <X className="size-3.5" />
                      Cancel takeover
                    </Button>
                  )}
                  {canTakeover && tk.can_reject && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 border-destructive/40 text-destructive hover:text-destructive"
                      data-testid="takeover-reject"
                      disabled={rejectMutation.isPending}
                      onClick={() => handleRejectTakeover(tk.request_id)}
                    >
                      <Ban className="size-3.5" />
                      Reject
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* Intervention tickets carry no inline actions: the row opens the
                ticket drawer, where replying and resolving live (journey steps
                5-7). Everything else keeps its inline action set. */}
            <div className="flex flex-wrap items-center gap-2">
              {ticket ? null : isTeam ? (
                !tk && canTakeover && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7"
                    data-guide-target="dashboard.sla-tasks.takeover"
                    disabled={rowBusy}
                    onClick={(e) => {
                      e.stopPropagation();
                      setTakeoverTarget(teamItem);
                    }}
                  >
                    <UserRoundPlus className="size-3.5" />
                    Takeover
                  </Button>
                )
              ) : (
                !form && (
                  <>
                    {canEscalate && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7"
                        data-guide-target="dashboard.sla-tasks.escalate"
                        disabled={atMaxTier}
                        title={atMaxTier ? 'Already at the maximum tier' : 'Escalate to the next tier'}
                        onClick={(e) => {
                          e.stopPropagation();
                          setEscalateReason('');
                          setEscalateTarget(mineItem);
                        }}
                      >
                        <TrendingUp className="size-3.5" />
                        Escalate
                      </Button>
                    )}
                    {canResolve && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7"
                        data-guide-target="dashboard.sla-tasks.resolve"
                        onClick={(e) => {
                          e.stopPropagation();
                          setResolveTarget(mineItem);
                        }}
                      >
                        <CheckCircle2 className="size-3.5" />
                        Resolve
                      </Button>
                    )}
                  </>
                )
              )}
              {/* Extend the resolution deadline. Only on My Pending rows (the
                  viewer owns them → assignee gate satisfied). /my-pending now emits
                  due_at_resolution, so gate strictly: hidden when there is no
                  resolution deadline. The dialog shows it as "Current due". */}
              {!isTeam && !ticket && canExtend && (
                <ExtendDueButton
                  trackingId={item.id}
                  isResolved={false}
                  isAssignee
                  takeoverPending={!!tk}
                  currentDueAt={mineItem.due_at_resolution ?? null}
                  label={`${typeLabel}${item.reference ? ` · ${item.reference}` : ''}`}
                  variant="ghost"
                  onExtended={() => void load()}
                />
              )}
              {/* Reassign is locked while a takeover is pending (soft lock). */}
              {!tk && !ticket && canReassign && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7"
                  data-guide-target="dashboard.sla-tasks.reassign"
                  disabled={rowBusy}
                  onClick={(e) => {
                    e.stopPropagation();
                    setReassignTarget({
                      id: item.id,
                      label: `${typeLabel}${item.reference ? ` · ${item.reference}` : ''}`,
                    });
                  }}
                >
                  <UserRoundCog className="size-3.5" />
                  Reassign
                </Button>
              )}
            </div>
          </div>
        </div>
      </li>
    );
  };

  const renderPager = (cur: number, count: number, totalCount: number) => (
    <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
      <span>
        {totalCount === 0
          ? '0 of 0'
          : `${cur * PAGE_SIZE + 1}–${Math.min((cur + 1) * PAGE_SIZE, totalCount)} of ${totalCount}`}
      </span>
      {totalCount > PAGE_SIZE && (
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-7"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={cur === 0}
            aria-label="Previous page"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="size-7"
            onClick={() => setPage((p) => Math.min(count - 1, p + 1))}
            disabled={cur >= count - 1}
            aria-label="Next page"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Clock className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">
          {mode === 'mine' ? 'My pending tasks' : mode === 'team' ? 'My team tasks' : 'Coverage'}
        </h2>
        {mode === 'mine' && mineItems !== null && (
          <Badge variant="secondary" className="ml-1">
            {mineItems.length}
          </Badge>
        )}
        {mode === 'team' && teamItems !== null && (
          <Badge variant="secondary" className="ml-1">
            {teamItems.length}
          </Badge>
        )}
        <div className="ml-auto inline-flex rounded-md border p-0.5">
          <Button
            type="button"
            size="sm"
            variant={mode === 'mine' ? 'primary' : 'ghost'}
            className="h-7 px-2.5"
            onClick={() => setMode('mine')}
          >
            My Pending
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === 'team' ? 'primary' : 'ghost'}
            className="h-7 px-2.5"
            onClick={() => setMode('team')}
          >
            My Team
          </Button>
          <Button
            type="button"
            size="sm"
            data-guide-target="dashboard.coverage.tab"
            variant={mode === 'coverage' ? 'primary' : 'ghost'}
            className="h-7 px-2.5"
            onClick={() => setMode('coverage')}
          >
            Coverage
          </Button>
        </div>
      </div>

      {mode !== 'coverage' && activeLoaded && (
        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by number, contact, or type…"
            className="h-8 pl-8 text-sm"
          />
        </div>
      )}

      {banner && (
        <div
          data-testid="takeover-banner"
          className="takeover-flash mb-3 rounded-lg border-2 border-amber-400 bg-amber-50/70 p-3 dark:bg-amber-950/30"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold">
                {humanizeType(banner as unknown as AnyTask)}
                {banner.reference ? (
                  <span className="text-muted-foreground"> · {banner.reference}</span>
                ) : null}
              </p>
              {banner.takeover?.status === 'pending' ? (
                <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-400">
                  {banner.takeover.initiator_name} wants to take over this task.
                </p>
              ) : (
                <p className="mt-0.5 text-xs text-muted-foreground">
                  This takeover is {banner.takeover?.status ?? 'no longer pending'}.
                </p>
              )}
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="size-6 shrink-0"
              aria-label="Dismiss"
              onClick={clearTakeoverParam}
            >
              <X className="size-4" />
            </Button>
          </div>
          {banner.takeover?.status === 'pending' && (
            <div className="mt-2">
              <TakeoverCountdown
                commitAt={banner.takeover.commit_at}
                windowSeconds={banner.takeover.window_seconds}
                onExpire={() => {
                  if (takeoverParam) getTakeoverState(takeoverParam).then(setBanner).catch(() => {});
                }}
              />
              {banner.takeover.can_reject && (
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2 h-7 border-destructive/40 text-destructive hover:text-destructive"
                  data-testid="takeover-banner-reject"
                  disabled={rejectMutation.isPending}
                  onClick={() => handleRejectTakeover(banner.takeover!.request_id, true)}
                >
                  <Ban className="size-3.5" />
                  Reject takeover
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {mode === 'coverage' ? (
        // Coverage management lives as a third tab so the dashboard stays one compact
        // surface. One unified form: coverer (defaults to "You"; managers can change it)
        // → covered. Self-vs-team is hidden behind a single mental model.
        <CoverageManager canManageTeam={canManageTeamCoverage} />
      ) : mode === 'team' ? (
        teamError ? (
          <p className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="size-4" /> {teamError}
          </p>
        ) : teamItems === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : teamItems.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CheckCircle2 className="size-4 text-emerald-600" />
            No open tasks across your teams.
          </p>
        ) : teamPageItems.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tasks match “{search}”.</p>
        ) : (
          <>
            <ul className="divide-y">{teamPageItems.map(renderRow)}</ul>
            {renderPager(teamCurrentPage, teamPageCount, teamTotal)}
          </>
        )
      ) : error ? (
        <p className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" /> {error}
        </p>
      ) : mineItems === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : mineItems.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-emerald-600" />
          Nothing pending — you&apos;re all caught up.
        </p>
      ) : pageItems.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tasks match “{search}”.</p>
      ) : (
        <>
          <ul className="divide-y">{pageItems.map(renderRow)}</ul>
          {renderPager(currentPage, pageCount, total)}
        </>
      )}

      <AlertDialog open={!!takeoverTarget} onOpenChange={(o) => !o && setTakeoverTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Take over this task?</AlertDialogTitle>
            <AlertDialogDescription>
              {takeoverTarget
                ? `${humanizeType(takeoverTarget)}${takeoverTarget.reference ? ` · ${takeoverTarget.reference}` : ''} — currently with ${takeoverTarget.assignee_name ?? 'a teammate'}. It will move to your pending tasks at your tier. The SLA clock is not reset.`
                : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={takeoverMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmTakeover();
              }}
              disabled={takeoverMutation.isPending}
            >
              {takeoverMutation.isPending ? 'Taking over…' : 'Take over'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!resolveTarget} onOpenChange={(o) => !o && setResolveTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark as resolved</AlertDialogTitle>
            <AlertDialogDescription>
              This stops the SLA clock and closes the conversation in Respond. This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resolving}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); void handleResolve(); }} disabled={resolving}>
              {resolving ? 'Resolving…' : 'Confirm'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog
        open={!!escalateTarget}
        onOpenChange={(o) => {
          if (!o) {
            setEscalateTarget(null);
            setEscalateReason('');
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Escalate to tier {(escalateTarget?.current_tier ?? 1) + 1}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-1">
            <Label htmlFor="pending-escalate-reason">Reason</Label>
            <Input
              id="pending-escalate-reason"
              placeholder="Why escalate now?"
              value={escalateReason}
              onChange={(e) => setEscalateReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && escalateReason.trim() && !escalating) {
                  e.preventDefault();
                  void handleEscalate();
                }
              }}
              autoFocus
            />
            <p className="text-xs text-muted-foreground">
              Moves this conversation to the next tier and reassigns per policy. The new assignee is
              notified.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setEscalateTarget(null);
                setEscalateReason('');
              }}
              disabled={escalating}
            >
              Cancel
            </Button>
            <Button onClick={() => void handleEscalate()} disabled={escalating || !escalateReason.trim()}>
              {escalating ? 'Escalating…' : 'Escalate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ReassignDialog
        open={!!reassignTarget}
        onOpenChange={(o) => !o && setReassignTarget(null)}
        taskLabel={reassignTarget?.label}
        submitting={reassignMutation.isPending}
        onConfirm={handleReassignConfirm}
      />

      {/* The enquiry is answered here, in place - no navigation, no Respond inbox. */}
      <InterventionTicketDrawer
        ticketId={openTicketId}
        open={!!openTicketId}
        onOpenChange={(o) => {
          if (o) return;
          setOpenTicketId(null);
          // A reply in the drawer stops this ticket's response clock: re-read the
          // row so the chips agree with what just happened.
          void load();
        }}
        onResolved={() => void load()}
      />
    </div>
  );
}
