'use client';

/**
 * Portal landing content - shared by the stable slug tree
 * (`/portal/c/{slug}`) and the legacy `/portal` tree (impersonation + old
 * links). All navigation goes through lib/portal-paths so links stay inside
 * the active tree.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, Copy, FileText, LogOut, Plus, Star } from 'lucide-react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import type { ListBoardViewMode } from '@/hooks/useListBoardViewPreference';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/lib/toast';
import {
  GATED_LANDING_KINDS,
  LANDING_LABELS,
  PortalContact,
  PortalLandingKind,
  PortalSubmissionKind,
  PortalSubmissionSummary,
  PortalUnauthorizedError,
  SUBMISSION_KINDS,
  clearPortalToken,
  fetchMeWithGrace,
  fetchSubmissions,
  isLandingKind,
  isSubmissionKind,
  portalLogout,
  readPortalToken,
  statusLabel,
} from '../lib/portal-client';
import { listRequestsAsSummaries } from '../lib/price-tag-request-service';
import {
  complaintStatusLabel,
  complaintStatusPillClass,
} from '@/lib/complaint-status';
import { revisionBadgeLabel } from '@/lib/document-number';
import {
  portalDetailPath,
  portalDuplicatePath,
  portalNewPath,
  portalRevisePath,
  portalVerifyPath,
} from '../lib/portal-paths';
import { useRevisionPolicy } from '../hooks/useRevisions';
import { ReviseAction } from './ReviseAction';
import { LandingToolbar } from './LandingToolbar';
import {
  DEFAULT_LANDING_SORT,
  activeLandingFilterCount,
  applyLandingFilters,
  landingFieldsFor,
  sortLandingItems,
  type LandingFilters,
  type LandingSort,
} from '../lib/landing-fields';

// Shared across every kind, so the choice survives a type switch (AC-L7).
const PORTAL_VIEW_KEY = 'sorento.portalView';

// Display order differs from the canonical list: stock inquiry first.
const TYPES: PortalSubmissionKind[] = [
  'stock_inquiry',
  ...SUBMISSION_KINDS.filter((k) => k !== 'stock_inquiry'),
];

/**
 * The dropdown's option list for THIS contact (D45): the four ungated kinds,
 * then every gated form the contact's access types (or an override) grant.
 * The server enforces the same rule on every route regardless, so this only
 * decides what is offered, never what is allowed.
 */
function landingKindsFor(contact: PortalContact | null): PortalLandingKind[] {
  const granted = GATED_LANDING_KINDS.filter((k) =>
    contact?.visible_form_types?.includes(k),
  );
  return [...TYPES, ...granted];
}

const EMPTY_LISTS: Record<PortalLandingKind, PortalSubmissionSummary[]> = {
  complaint: [],
  stock_inquiry: [],
  purchase_request: [],
  sponsorship_form: [],
  price_tag_request: [],
};

type BadgeVariant =
  | 'primary'
  | 'secondary'
  | 'destructive'
  | 'success'
  | 'warning'
  | 'info';

// Status → badge colour. draft is intentionally neutral (no colour) so it
// reads as "not yet meaningful". The other states map to a unique colour so
// users can scan a list without reading labels.
function statusVariant(row: PortalSubmissionSummary): BadgeVariant {
  if (row.is_draft) return 'secondary';
  const s = (row.status || '').toLowerCase();
  if (s === 'rejected' || s === 'cancelled') return 'destructive';
  if (
    s === 'approved' ||
    s === 'completed' ||
    s === 'fulfilled' ||
    s === 'settled_on_site' ||
    s === 'closed'
  ) {
    return 'success';
  }
  if (s === 'responded' || s === 'replied') return 'info';
  return 'primary';
}

// Tailwind classes that tint the card background + border by status. Kept
// subtle so text stays legible.
function statusCardClass(row: PortalSubmissionSummary): string {
  if (row.is_draft) {
    return 'bg-card border-border';
  }
  const s = (row.status || '').toLowerCase();
  if (s === 'rejected' || s === 'cancelled') {
    return 'bg-destructive/5 border-destructive/40';
  }
  if (
    s === 'approved' ||
    s === 'completed' ||
    s === 'fulfilled' ||
    s === 'settled_on_site' ||
    s === 'closed'
  ) {
    return 'bg-success/5 border-success/40';
  }
  if (s === 'responded' || s === 'replied') {
    return 'bg-violet-50 border-violet-200 dark:bg-violet-950/30 dark:border-violet-900';
  }
  return 'bg-primary/5 border-primary/30';
}

// Per-kind primary/secondary metadata picked for the compact card layout.
function pickCardMeta(row: PortalSubmissionSummary): {
  product?: string;
  project?: string;
  customer?: string;
} {
  if (row.kind === 'complaint') {
    return {
      product: row.product_code ?? undefined,
      project: row.project_title ?? undefined,
      customer: row.customer_name ?? undefined,
    };
  }
  if (row.kind === 'stock_inquiry') {
    return {
      product: row.product_code ?? undefined,
      project: row.project_name ?? undefined,
      customer: row.project_customer ?? undefined,
    };
  }
  if (row.kind === 'price_tag_request') {
    return { customer: row.customer_name ?? undefined };
  }
  return {
    project: row.project_title ?? row.sponsor_subject ?? undefined,
    customer: row.customer_name ?? undefined,
  };
}

export function PortalLanding({ slug }: { slug?: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [contact, setContact] = useState<PortalContact | null>(null);
  const [submissions, setSubmissions] =
    useState<Record<PortalLandingKind, PortalSubmissionSummary[]>>(EMPTY_LISTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debouncedSearch,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const initialTabFromUrl = (() => {
    const t = searchParams?.get('type');
    return isLandingKind(t) ? t : 'stock_inquiry';
  })();
  const [activeTab, setActiveTab] =
    useState<PortalLandingKind>(initialTabFromUrl);
  // Filter + sort are component state that resets whenever the type changes
  // (D-L4) - the field set differs per kind, so a status or field value
  // picked for one kind has no business surviving a tab switch. The view
  // choice (cards vs list) is the one thing that persists, per device,
  // across both a reload and a type switch (AC-L7).
  const [filters, setFilters] = useState<LandingFilters>({});
  const [sort, setSort] = useState<LandingSort>(DEFAULT_LANDING_SORT);
  useEffect(() => {
    setFilters({});
    setSort(DEFAULT_LANDING_SORT);
  }, [activeTab]);
  const [view, setViewState] = useState<ListBoardViewMode>('board');
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(PORTAL_VIEW_KEY);
    if (stored === 'list' || stored === 'board') {
      setViewState(stored);
      return;
    }
    // Tailwind's `md:` breakpoint (768px) - a media query, not innerWidth, so
    // it stays live if the window is resized before the first pick is made.
    setViewState(window.matchMedia('(min-width: 768px)').matches ? 'list' : 'board');
  }, []);
  const setView = useCallback((mode: ListBoardViewMode) => {
    setViewState(mode);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(PORTAL_VIEW_KEY, mode);
    }
  }, []);
  const userPickedTabRef = useRef<boolean>(Boolean(searchParams?.get('type')));
  // Mirror current URL `?type=` so loadAll's expired-token redirect can read it
  // without depending on `searchParams` (which would re-create loadAll and
  // break the debounced search).
  const typeQueryRef = useRef<string | null>(searchParams?.get('type') ?? null);
  useEffect(() => {
    typeQueryRef.current = searchParams?.get('type') ?? null;
  }, [searchParams]);

  const landingKinds = useMemo(() => landingKindsFor(contact), [contact]);

  // A `?type=` deep link, or a starred default, can name a gated kind this
  // contact does not hold - a link forwarded by a colleague, or a grant since
  // withdrawn. Fall back to the first ungated kind rather than showing an
  // option whose list the server would refuse (D45).
  useEffect(() => {
    if (!contact) return;
    if (landingKinds.includes(activeTab)) return;
    setActiveTab('stock_inquiry');
  }, [contact, landingKinds, activeTab]);

  // Once the contact is known (and the URL has no `?type=` deep-link, and the
  // user hasn't manually switched tabs in this session), apply any default
  // tab the contact previously starred.
  useEffect(() => {
    if (!contact?.contact_id) return;
    if (userPickedTabRef.current) return;
    if (searchParams?.get('type')) return;
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(
      `sorento.portalDefaultTab.${contact.contact_id}`,
    );
    if (isLandingKind(stored) && landingKinds.includes(stored)) {
      setActiveTab(stored);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contact?.contact_id, landingKinds]);

  const handleTabChange = useCallback((next: PortalLandingKind) => {
    userPickedTabRef.current = true;
    setActiveTab(next);
  }, []);

  const defaultTabKey = useMemo(() => {
    if (!contact?.contact_id) return null;
    return `sorento.portalDefaultTab.${contact.contact_id}`;
  }, [contact?.contact_id]);

  const [savedDefaultTab, setSavedDefaultTab] =
    useState<PortalLandingKind | null>(null);
  useEffect(() => {
    if (!defaultTabKey || typeof window === 'undefined') {
      setSavedDefaultTab(null);
      return;
    }
    const stored = window.localStorage.getItem(defaultTabKey);
    setSavedDefaultTab(isLandingKind(stored) ? stored : null);
  }, [defaultTabKey]);

  const handleSetDefaultTab = useCallback(() => {
    if (!defaultTabKey || typeof window === 'undefined') return;
    window.localStorage.setItem(defaultTabKey, activeTab);
    setSavedDefaultTab(activeTab);
    toast.success(`${LANDING_LABELS[activeTab]} is now your default tab.`);
  }, [activeTab, defaultTabKey]);

  // Track whether the very first load has finished. Subsequent search
  // refetches must NOT flip `loading` back to true, otherwise the skeleton
  // remounts and the search Input loses focus on every keystroke.
  const initialLoadDone = useRef(false);

  // Keep tab in sync if the user navigates back with a different ?type=.
  useEffect(() => {
    const t = searchParams?.get('type');
    if (isLandingKind(t) && t !== activeTab) setActiveTab(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const loadAll = useCallback(
    async (q?: string) => {
      const existing = readPortalToken();
      if (!existing) {
        router.replace(portalVerifyPath({ slug: slug ?? null }));
        return;
      }
      const isInitial = !initialLoadDone.current;
      if (isInitial) setLoading(true);
      try {
        // fetchMeWithGrace absorbs the post-verify commit-visibility race
        // (fresh token transiently 401s) before bouncing back to verify.
        const me = await fetchMeWithGrace();
        setContact(me);
        // The gated kinds answer their own endpoints in their own shapes, so
        // each brings its own adapter (D45) and is only asked for when the
        // contact holds the grant.
        const wantsPriceTags = Boolean(
          me.visible_form_types?.includes('price_tag_request'),
        );
        // allSettled, not all: the legs are independent lists and one of them
        // answering 403 or 500 used to reject the whole load, so the landing
        // showed its error screen and the four kinds that answered perfectly
        // well were unreachable. A leg that fails is that kind empty.
        const legs = await Promise.allSettled([
          ...TYPES.map((t) => fetchSubmissions(t, q)),
          wantsPriceTags ? listRequestsAsSummaries(q) : Promise.resolve([]),
        ]);

        // An expired token is not one kind failing - every leg would fail and
        // the answer is to re-verify - so it is rethrown to the handler below.
        const dead = legs.find(
          (leg) =>
            leg.status === 'rejected' &&
            leg.reason instanceof PortalUnauthorizedError,
        );
        if (dead && dead.status === 'rejected') throw dead.reason;

        const rowsOf = (index: number): PortalSubmissionSummary[] => {
          const leg = legs[index];
          if (leg.status === 'fulfilled') return leg.value;
          console.warn('Portal landing: one list failed to load', leg.reason);
          return [];
        };

        setSubmissions({
          stock_inquiry: rowsOf(0),
          complaint: rowsOf(1),
          purchase_request: rowsOf(2),
          sponsorship_form: rowsOf(3),
          price_tag_request: rowsOf(4),
        });
        setError(null);
        // Token validated - clear the freshness stamp so subsequent transient
        // 401s (e.g. real expiry) bounce back immediately without retry.
        if (typeof window !== 'undefined') {
          window.sessionStorage.removeItem('sorento.portalTokenWrittenAt');
        }
      } catch (e) {
        if (e instanceof PortalUnauthorizedError) {
          // Token expired/revoked. The slug tree recovers identity from the
          // slug itself; the legacy tree forwards the dead token so
          // /portal/verify can look up contact/space via /token-info.
          router.replace(
            portalVerifyPath({
              slug: slug ?? null,
              reason: 'expired',
              token: existing,
              type: typeQueryRef.current,
            }),
          );
          return;
        }
        setError(e instanceof Error ? e.message : 'Failed to load portal.');
      } finally {
        if (isInitial) {
          setLoading(false);
          initialLoadDone.current = true;
        }
      }
    },
    [router, slug],
  );

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // Debounced refetch when the user types in the search box (M6-06:
  // useDebouncedSearch, the shared 200ms standard); backend now does the
  // field-spanning search so the result reflects every column (product,
  // metadata, doc number, etc.).
  useEffect(() => {
    void loadAll(debouncedSearch);
  }, [debouncedSearch, loadAll]);

  const totals = useMemo(() => {
    const out: Record<PortalLandingKind, number> = {
      complaint: 0,
      stock_inquiry: 0,
      purchase_request: 0,
      sponsorship_form: 0,
      price_tag_request: 0,
    };
    for (const t of landingKinds) out[t] = submissions[t]?.length ?? 0;
    return out;
  }, [submissions, landingKinds]);

  const handleLogout = useCallback(async () => {
    const t = readPortalToken();
    // Revoke server-side first (best-effort) - clearing storage alone would
    // leave a copied token valid until expiry.
    try {
      await portalLogout();
    } catch {
      // best-effort
    }
    clearPortalToken();
    const qs = !slug && t ? t : null;
    router.replace(
      portalVerifyPath({ slug: slug ?? null, reason: 'logout', token: qs }),
    );
  }, [router, slug]);

  if (loading) {
    return (
      <div className="w-full max-w-3xl mx-auto px-3 pt-4 pb-4 space-y-3">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-3xl mx-auto px-3 pt-4 pb-4 space-y-3">
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
        <Button
          variant="outline"
          onClick={() =>
            router.replace(portalVerifyPath({ slug: slug ?? null }))
          }
        >
          Verify with OTP
        </Button>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto px-3 pt-3 pb-4 space-y-3">
      {/* Header - Welcome centered, Log out anchored to top-right. */}
      <div className="relative flex items-center justify-center min-h-[2.75rem]">
        <h1 className="text-lg font-semibold text-center break-words px-12">
          Welcome{contact?.name ? `, ${contact.name}` : ''}
        </h1>
        <Button
          variant="outline"
          size="sm"
          onClick={handleLogout}
          className="absolute right-0 top-1/2 -translate-y-1/2 h-9 px-2.5"
          aria-label="Log out"
          title="Log out"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>

      {/* Search input only (D-L3) - the status filter now lives in the
          toolbar's Filter popover, alongside every other filterable field. */}
      <ListSearchInput
        value={search}
        onChange={setSearch}
        isSettling={searchSettling}
        placeholder="Search..."
        aria-label="Search submissions"
        className="w-full"
        inputClassName="h-12 text-base"
      />

      <div className="flex items-stretch gap-2">
        <SearchableSelect
          value={activeTab}
          onChange={(v) => handleTabChange(v as PortalLandingKind)}
          options={landingKinds.map((t) => ({
            value: t,
            label: LANDING_LABELS[t],
          }))}
          size="lg"
          triggerClassName="flex-1 min-h-12 text-base"
          renderTriggerLabel={(opt) => {
            const t = opt.value as PortalLandingKind;
            return (
              <span className="flex items-center gap-2">
                {LANDING_LABELS[t]}
                <Badge variant="secondary" className="px-1.5 py-0 text-xs">
                  {totals[t]}
                </Badge>
                {savedDefaultTab === t && (
                  <Star
                    className="h-3.5 w-3.5 fill-yellow-400 text-yellow-500 shrink-0"
                    aria-label="default"
                  />
                )}
              </span>
            );
          }}
          renderOption={(opt) => {
            const t = opt.value as PortalLandingKind;
            return (
              <span className="flex items-center gap-2">
                {LANDING_LABELS[t]}
                <Badge variant="secondary" className="px-1.5 py-0 text-xs">
                  {totals[t]}
                </Badge>
                {savedDefaultTab === t && (
                  <Star
                    className="h-3.5 w-3.5 fill-yellow-400 text-yellow-500 shrink-0"
                    aria-label="default"
                  />
                )}
              </span>
            );
          }}
        />
        <Button
          type="button"
          variant="outline"
          onClick={handleSetDefaultTab}
          disabled={!contact || savedDefaultTab === activeTab}
          aria-label={
            savedDefaultTab === activeTab
              ? `${LANDING_LABELS[activeTab]} is your default tab`
              : `Set ${LANDING_LABELS[activeTab]} as default tab`
          }
          title={
            savedDefaultTab === activeTab
              ? 'Default tab'
              : 'Set as default for this contact'
          }
          className="h-12 px-3"
        >
          <Star
            className={`h-4 w-4 ${
              savedDefaultTab === activeTab
                ? 'fill-yellow-400 text-yellow-500'
                : ''
            }`}
          />
        </Button>
      </div>

      <SubmissionList
        kind={activeTab}
        items={submissions[activeTab] ?? []}
        filters={filters}
        onFiltersChange={setFilters}
        sort={sort}
        onSortChange={setSort}
        view={view}
        onViewChange={setView}
        slug={slug}
        search={search}
        onClearSearch={() => setSearch('')}
      />
    </div>
  );
}

function SubmissionList({
  kind,
  items,
  filters,
  onFiltersChange,
  sort,
  onSortChange,
  view,
  onViewChange,
  slug,
  search,
  onClearSearch,
}: {
  kind: PortalLandingKind;
  items: PortalSubmissionSummary[];
  filters: LandingFilters;
  onFiltersChange: (next: LandingFilters) => void;
  sort: LandingSort;
  onSortChange: (next: LandingSort) => void;
  view: ListBoardViewMode;
  onViewChange: (mode: ListBoardViewMode) => void;
  slug?: string;
  /** A search term is answered server-side (`fetchSubmissions(kind, q)`),
   *  so a search-only zero result already arrives as `items.length === 0`
   *  with no client-side `filters` set at all (review round 2, AC-L8) - the
   *  empty state has to know about it too, not just `filters`. */
  search?: string;
  onClearSearch?: () => void;
}) {
  const fields = useMemo(() => landingFieldsFor(kind), [kind]);
  const filtered = useMemo(
    () => sortLandingItems(applyLandingFilters(items, fields, filters), fields, sort),
    [items, fields, filters, sort],
  );

  const [previewRow, setPreviewRow] = useState<PortalSubmissionSummary | null>(
    null,
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <LandingToolbar
          fields={fields}
          items={items}
          filters={filters}
          onFiltersChange={onFiltersChange}
          sort={sort}
          onSortChange={onSortChange}
          view={view}
          onViewChange={onViewChange}
        />
        <Button asChild size="sm" className="shrink-0 max-w-[7.5rem] sm:max-w-none">
          <Link href={portalNewPath(kind, slug)}>
            <Plus className="shrink-0" />
            {/* Review round 2: "New Price Tag Request" (the longest label)
                pushed the toolbar onto two rows at 375px - truncated below
                `sm` (icon plus as much of the label as fits, at minimum
                "New"), the full label at `sm` and up. One text node, not a
                second element also reading "New" - that collided with a
                status pill of the same word elsewhere on the page. */}
            <span className="truncate">New {LANDING_LABELS[kind]}</span>
          </Link>
        </Button>
      </div>
      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground space-y-2">
            <FileText className="h-8 w-8 mx-auto" />
            {items.length === 0 &&
            !(search ?? '').trim() &&
            activeLandingFilterCount(filters) === 0 ? (
              <p>No {LANDING_LABELS[kind].toLowerCase()} submissions yet.</p>
            ) : (
              <>
                <p>No submissions match your filters.</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    onFiltersChange({});
                    onClearSearch?.();
                  }}
                >
                  Clear filters
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      ) : view === 'list' ? (
        <ul className="space-y-1.5">
          {filtered.map((row) => (
            <li key={row.id}>
              <SubmissionRow
                row={row}
                kind={kind}
                slug={slug}
                onLongPress={() => setPreviewRow(row)}
              />
            </li>
          ))}
        </ul>
      ) : (
        <ul className="space-y-2.5">
          {filtered.map((row) => (
            <li key={row.id}>
              <SubmissionCard
                row={row}
                kind={kind}
                slug={slug}
                onLongPress={() => setPreviewRow(row)}
              />
            </li>
          ))}
        </ul>
      )}

      <SubmissionPreviewDialog
        row={previewRow}
        kind={kind}
        slug={slug}
        onOpenChange={(open) => !open && setPreviewRow(null)}
      />
    </div>
  );
}

/**
 * Click / long-press / keyboard wiring shared by SubmissionCard and
 * SubmissionRow (D-L5) - both open the detail page on a tap/click/Enter and
 * the preview dialog on a long-press, right-click or context-menu key.
 */
function useSubmissionPress({
  kind,
  id,
  slug,
  onLongPress,
}: {
  kind: PortalLandingKind;
  id: string;
  slug?: string;
  onLongPress: () => void;
}) {
  const router = useRouter();
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  const startPress = () => {
    longPressFired.current = false;
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      onLongPress();
    }, 450);
  };
  const clearPress = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  return {
    role: 'link' as const,
    tabIndex: 0,
    onClick: () => {
      if (longPressFired.current) {
        longPressFired.current = false;
        return;
      }
      router.push(portalDetailPath(kind, id, slug));
    },
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        router.push(portalDetailPath(kind, id, slug));
      }
    },
    onContextMenu: (e: React.MouseEvent) => {
      e.preventDefault();
      onLongPress();
    },
    onTouchStart: startPress,
    onTouchEnd: clearPress,
    onTouchMove: clearPress,
    onTouchCancel: clearPress,
    onMouseDown: startPress,
    onMouseUp: clearPress,
    onMouseLeave: clearPress,
  };
}

function SubmissionRow({
  row,
  kind,
  slug,
  onLongPress,
}: {
  row: PortalSubmissionSummary;
  kind: PortalLandingKind;
  slug?: string;
  onLongPress: () => void;
}) {
  const press = useSubmissionPress({ kind, id: row.id, slug, onLongPress });
  const meta = pickCardMeta(row);
  const primaryMeta = meta.product ?? meta.project ?? meta.customer ?? null;
  const primary = row.document_number ?? row.title ?? '-';
  const isComplaint = row.kind === 'complaint';
  const statusText = row.is_draft
    ? 'Draft'
    : isComplaint
      ? complaintStatusLabel(row.status)
      : statusLabel(row.status);
  const createdText = row.created_at
    ? new Date(row.created_at).toLocaleDateString(undefined, {
        dateStyle: 'medium',
      })
    : null;
  // Review round 2: same formatting as createdText - the list row used to
  // print the raw ISO string here instead.
  const neededByText = row.needed_by_date
    ? new Date(row.needed_by_date).toLocaleDateString(undefined, {
        dateStyle: 'medium',
      })
    : null;

  return (
    <div
      {...press}
      className="flex items-center gap-2 overflow-hidden rounded-lg border bg-card px-3 py-2 hover:brightness-95 active:brightness-90 transition-[filter] select-none cursor-pointer"
    >
      {isComplaint && !row.is_draft ? (
        <span
          className={`max-w-[40%] shrink-0 inline-flex items-center truncate rounded-md px-2 py-0.5 text-xs font-semibold ${complaintStatusPillClass(row.status)}`}
          title={statusText}
        >
          {statusText}
        </span>
      ) : (
        <Badge
          variant={statusVariant(row)}
          className="max-w-[40%] shrink-0 truncate"
          title={statusText}
        >
          {statusText}
        </Badge>
      )}
      <span
        className="min-w-0 flex-[2] truncate text-sm font-medium"
        title={primary}
      >
        {primary}
      </span>
      <span
        className="min-w-0 flex-1 truncate text-sm text-muted-foreground"
        title={primaryMeta ?? undefined}
      >
        {primaryMeta}
      </span>
      {neededByText && (
        <span
          className="shrink-0 w-20 truncate text-right text-xs text-muted-foreground"
          title={neededByText}
        >
          {neededByText}
        </span>
      )}
      <span
        className="shrink-0 w-20 truncate text-right text-xs text-muted-foreground"
        title={createdText ?? undefined}
      >
        {createdText}
      </span>
    </div>
  );
}

function SubmissionCard({
  row,
  kind,
  slug,
  onLongPress,
}: {
  row: PortalSubmissionSummary;
  kind: PortalLandingKind;
  slug?: string;
  onLongPress: () => void;
}) {
  const press = useSubmissionPress({ kind, id: row.id, slug, onLongPress });
  const meta = pickCardMeta(row);
  const primary = row.document_number ?? row.title ?? '-';
  const tintClass = statusCardClass(row);

  // Complaints use the shared status map so portal labels + colours tally with
  // the internal system view; other kinds keep the generic badge variant.
  const isComplaint = row.kind === 'complaint';
  const statusText = row.is_draft
    ? 'Draft'
    : isComplaint
      ? complaintStatusLabel(row.status)
      : statusLabel(row.status);

  return (
    <div
      {...press}
      className={`relative block rounded-lg border ${tintClass} px-3.5 py-3 pr-3 hover:brightness-95 active:brightness-90 transition-[filter] select-none cursor-pointer`}
    >
      {/* Status badge anchored top-right; allows multi-word status to wrap
          onto two lines without colliding with the primary text. */}
      {isComplaint && !row.is_draft ? (
        <span
          className={`absolute top-2 right-2 max-w-[45%] inline-flex items-center justify-end rounded-md px-2 py-0.5 text-xs font-semibold whitespace-normal text-right leading-tight ${complaintStatusPillClass(row.status)}`}
        >
          {statusText}
        </span>
      ) : (
        <Badge
          variant={statusVariant(row)}
          className="absolute top-2 right-2 max-w-[45%] whitespace-normal text-right leading-tight justify-end"
        >
          {statusText}
        </Badge>
      )}
      <div className="space-y-1 pr-[45%]">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="text-base font-semibold break-words" title={primary}>
            {primary}
          </p>
          {revisionBadgeLabel(row.revision_no) && (
            <Badge variant="secondary">
              {revisionBadgeLabel(row.revision_no)}
            </Badge>
          )}
          {row.has_revision_draft && (
            <Badge variant="warning" data-testid="revising-chip">
              Revising
            </Badge>
          )}
        </div>
      </div>
      <div className="space-y-1 mt-1">
        {meta.product && (
          <p
            className="text-sm text-foreground/80 break-words"
            title={meta.product}
          >
            <span className="text-muted-foreground">Product: </span>
            {meta.product}
          </p>
        )}
        {meta.project && (
          <p
            className="text-sm text-foreground/80 break-words"
            title={meta.project}
          >
            <span className="text-muted-foreground">Project: </span>
            {meta.project}
          </p>
        )}
        {meta.customer && (
          <p
            className="text-sm text-foreground/80 break-words"
            title={meta.customer}
          >
            <span className="text-muted-foreground">Customer: </span>
            {meta.customer}
          </p>
        )}
        {row.needed_by_date && (
          <p className="text-sm text-foreground/80">
            <span className="text-muted-foreground">Need by: </span>
            {row.needed_by_date}
          </p>
        )}
        {row.last_revised_at ? (
          <p className="text-xs text-muted-foreground">
            Revised{' '}
            {new Date(row.last_revised_at).toLocaleDateString(undefined, {
              dateStyle: 'medium',
            })}
          </p>
        ) : (
          row.created_at && (
            <p className="text-xs text-muted-foreground">
              {new Date(row.created_at).toLocaleDateString(undefined, {
                dateStyle: 'medium',
              })}
            </p>
          )
        )}
        {row.rejection_reason && (
          <p className="text-xs text-destructive line-clamp-2">
            {row.rejection_reason}
          </p>
        )}
      </div>
    </div>
  );
}

function SubmissionPreviewDialog({
  row,
  kind,
  slug,
  onOpenChange,
}: {
  row: PortalSubmissionSummary | null;
  kind: PortalLandingKind;
  slug?: string;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  // The list carries no policy block, so the card reads the same `revision`
  // block the detail page renders from. One GET, opened on long press only.
  // Revisions are a submission-kind mechanism: a gated kind has no such
  // endpoint, so it is asked for nothing rather than 404ing on every preview.
  const { policy } = useRevisionPolicy(
    isSubmissionKind(kind) ? kind : 'stock_inquiry',
    isSubmissionKind(kind) ? (row?.id ?? null) : null,
  );
  const meta = row
    ? pickCardMeta(row)
    : { product: undefined, project: undefined, customer: undefined };
  const entries: { label: string; value: string }[] = [];
  if (row) {
    if (row.document_number)
      entries.push({ label: 'Document number', value: row.document_number });
    if (row.title) entries.push({ label: 'Title', value: row.title });
    if (meta.product) entries.push({ label: 'Product', value: meta.product });
    if (meta.project) entries.push({ label: 'Project', value: meta.project });
    if (meta.customer)
      entries.push({ label: 'Customer', value: meta.customer });
    if (row.delivery_order_number)
      entries.push({ label: 'DO number', value: row.delivery_order_number });
    if (row.item_description)
      entries.push({ label: 'Item description', value: row.item_description });
    if (row.purpose) entries.push({ label: 'Purpose', value: row.purpose });
    if (row.reference && row.reference !== row.document_number) {
      entries.push({ label: 'Reference', value: row.reference });
    }
    if (row.created_at) {
      entries.push({
        label: 'Created',
        value: new Date(row.created_at).toLocaleString(undefined, {
          dateStyle: 'medium',
          timeStyle: 'short',
        }),
      });
    }
    if (row.rejection_reason)
      entries.push({ label: 'Rejection reason', value: row.rejection_reason });
  }

  return (
    <Dialog open={Boolean(row)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2 flex-wrap">
            <span className="break-words">
              {row?.document_number ?? row?.title ?? 'Submission'}
            </span>
            {row &&
              (row.kind === 'complaint' && !row.is_draft ? (
                <span
                  className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${complaintStatusPillClass(row.status)}`}
                >
                  {complaintStatusLabel(row.status)}
                </span>
              ) : (
                <Badge variant={statusVariant(row)}>
                  {row.is_draft ? 'Draft' : statusLabel(row.status)}
                </Badge>
              ))}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 min-h-0 overflow-y-auto space-y-3 -mx-1 px-1">
          {entries.map((e) => (
            <div key={e.label} className="space-y-0.5">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {e.label}
              </p>
              <p className="text-sm break-words whitespace-pre-wrap">
                {e.value}
              </p>
            </div>
          ))}
        </div>
        <ReviseAction
          policy={policy}
          onRevise={() => {
            if (row) router.push(portalRevisePath(kind, row.id, slug));
            onOpenChange(false);
          }}
          className="border-t pt-3"
        />
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="h-10"
          >
            Close
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              if (row) router.push(portalDuplicatePath(kind, row.id, slug));
              onOpenChange(false);
            }}
            className="h-10"
          >
            <Copy className="h-4 w-4 mr-2" />
            Duplicate
          </Button>
          <Button
            onClick={() => {
              if (row) router.push(portalDetailPath(kind, row.id, slug));
              onOpenChange(false);
            }}
            className="h-10"
          >
            Open
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
