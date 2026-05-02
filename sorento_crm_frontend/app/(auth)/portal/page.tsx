'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, Filter, FileText, LogOut, Plus, Star } from 'lucide-react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  PortalContact,
  PortalSubmissionKind,
  PortalSubmissionSummary,
  PortalUnauthorizedError,
  SUBMISSION_LABELS,
  clearPortalToken,
  fetchMe,
  fetchSubmissions,
  readPortalToken,
  statusLabel,
  writePortalToken,
} from './lib/portal-client';

const TYPES: PortalSubmissionKind[] = [
  'stock_inquiry',
  'complaint',
  'purchase_request',
  'sponsorship_form',
];

type StatusFilter = 'all' | 'draft' | 'submitted' | 'rejected';

type BadgeVariant = 'primary' | 'secondary' | 'destructive' | 'success' | 'warning' | 'info';

// Status → badge colour. draft is intentionally neutral (no colour) so it
// reads as "not yet meaningful". The other states map to a unique colour so
// users can scan a list without reading labels.
function statusVariant(row: PortalSubmissionSummary): BadgeVariant {
  if (row.is_draft) return 'secondary';
  const s = (row.status || '').toLowerCase();
  if (s === 'rejected' || s === 'cancelled') return 'destructive';
  if (s === 'approved' || s === 'completed' || s === 'fulfilled' || s === 'closed') {
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
  if (s === 'approved' || s === 'completed' || s === 'fulfilled' || s === 'closed') {
    return 'bg-success/5 border-success/40';
  }
  if (s === 'responded' || s === 'replied') {
    return 'bg-violet-50 border-violet-200 dark:bg-violet-950/30 dark:border-violet-900';
  }
  return 'bg-primary/5 border-primary/30';
}

function effectiveStatus(row: PortalSubmissionSummary): StatusFilter {
  if (row.is_draft) return 'draft';
  if (row.status === 'rejected') return 'rejected';
  return 'submitted';
}

// Per-kind primary/secondary metadata picked for the compact card layout.
function pickCardMeta(
  row: PortalSubmissionSummary,
): { product?: string; project?: string; customer?: string } {
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
  return {
    project: row.project_title ?? row.sponsor_subject ?? undefined,
    customer: row.customer_name ?? undefined,
  };
}

function isSubmissionKind(value: string | null | undefined): value is PortalSubmissionKind {
  return (
    value === 'complaint' ||
    value === 'stock_inquiry' ||
    value === 'purchase_request' ||
    value === 'sponsorship_form'
  );
}

function PortalLandingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [contact, setContact] = useState<PortalContact | null>(null);
  const [submissions, setSubmissions] = useState<Record<PortalSubmissionKind, PortalSubmissionSummary[]>>({
    complaint: [],
    stock_inquiry: [],
    purchase_request: [],
    sponsorship_form: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const initialTabFromUrl = (() => {
    const t = searchParams?.get('type');
    return isSubmissionKind(t) ? t : 'stock_inquiry';
  })();
  const [activeTab, setActiveTab] = useState<PortalSubmissionKind>(initialTabFromUrl);
  const userPickedTabRef = useRef<boolean>(Boolean(searchParams?.get('type')));
  // Mirror current URL `?type=` so loadAll's expired-token redirect can read it
  // without depending on `searchParams` (which would re-create loadAll and
  // break the debounced search).
  const typeQueryRef = useRef<string | null>(searchParams?.get('type') ?? null);
  useEffect(() => {
    typeQueryRef.current = searchParams?.get('type') ?? null;
  }, [searchParams]);

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
    if (isSubmissionKind(stored)) setActiveTab(stored);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contact?.contact_id]);

  const handleTabChange = useCallback((next: PortalSubmissionKind) => {
    userPickedTabRef.current = true;
    setActiveTab(next);
  }, []);

  const defaultTabKey = useMemo(() => {
    if (!contact?.contact_id) return null;
    return `sorento.portalDefaultTab.${contact.contact_id}`;
  }, [contact?.contact_id]);

  const [savedDefaultTab, setSavedDefaultTab] = useState<PortalSubmissionKind | null>(null);
  useEffect(() => {
    if (!defaultTabKey || typeof window === 'undefined') {
      setSavedDefaultTab(null);
      return;
    }
    const stored = window.localStorage.getItem(defaultTabKey);
    setSavedDefaultTab(isSubmissionKind(stored) ? stored : null);
  }, [defaultTabKey]);

  const handleSetDefaultTab = useCallback(() => {
    if (!defaultTabKey || typeof window === 'undefined') return;
    window.localStorage.setItem(defaultTabKey, activeTab);
    setSavedDefaultTab(activeTab);
    toast.success(`${SUBMISSION_LABELS[activeTab]} is now your default tab.`);
  }, [activeTab, defaultTabKey]);

  // Track whether the very first load has finished. Subsequent search
  // refetches must NOT flip `loading` back to true, otherwise the skeleton
  // remounts and the search Input loses focus on every keystroke.
  const initialLoadDone = useRef(false);

  // Pull token from URL on first load and persist to sessionStorage so reloads
  // (and child pages) don't need to keep it in the URL. `?type=` is left in
  // the URL so the deep-link tab still applies after the strip.
  useEffect(() => {
    const incoming = searchParams?.get('token');
    if (incoming) {
      writePortalToken(incoming);
      const url = new URL(window.location.href);
      url.searchParams.delete('token');
      router.replace(url.pathname + (url.search ? url.search : ''));
    }
  }, [router, searchParams]);

  // Keep tab in sync if the user navigates back with a different ?type=.
  useEffect(() => {
    const t = searchParams?.get('type');
    if (isSubmissionKind(t) && t !== activeTab) setActiveTab(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const loadAll = useCallback(async (q?: string) => {
    const existing = readPortalToken();
    if (!existing) {
      router.replace('/portal/verify');
      return;
    }
    // If the token was minted very recently (post-verify), give the BE a tiny
    // grace window before bouncing back to /portal/verify on a 401 — the
    // /verify-otp commit + a fast follow-up /me can race in some setups.
    const writtenAt =
      typeof window !== 'undefined'
        ? Number(window.sessionStorage.getItem('sorento.portalTokenWrittenAt') || '0')
        : 0;
    const tokenIsFresh = writtenAt > 0 && Date.now() - writtenAt < 30_000;
    const isInitial = !initialLoadDone.current;
    if (isInitial) setLoading(true);
    try {
      let me: PortalContact;
      try {
        me = await fetchMe();
      } catch (firstErr) {
        if (firstErr instanceof PortalUnauthorizedError && tokenIsFresh) {
          // /portalFetch already cleared the token on 401 — restore it for the
          // retry. If this also 401s, fall through to the bounce-back logic.
          writePortalToken(existing);
          await new Promise((r) => setTimeout(r, 500));
          me = await fetchMe();
        } else {
          throw firstErr;
        }
      }
      setContact(me);
      const lists = await Promise.all(TYPES.map((t) => fetchSubmissions(t, q)));
      setSubmissions({
        stock_inquiry: lists[0],
        complaint: lists[1],
        purchase_request: lists[2],
        sponsorship_form: lists[3],
      });
      setError(null);
      // Token validated — clear the freshness stamp so subsequent transient
      // 401s (e.g. real expiry) bounce back immediately without retry.
      if (typeof window !== 'undefined') {
        window.sessionStorage.removeItem('sorento.portalTokenWrittenAt');
      }
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        // The portal client cleared the (expired) token from sessionStorage
        // on 401, so forward it to /portal/verify via URL so it can look up
        // the contact/space pair via /token-info. Preserve `?type=` so the
        // user still lands on the deep-linked tab after re-verifying.
        const qs = new URLSearchParams({ reason: 'expired' });
        if (existing) qs.set('token', existing);
        const desiredType = typeQueryRef.current;
        if (desiredType && desiredType.trim()) qs.set('type', desiredType.trim());
        router.replace(`/portal/verify?${qs.toString()}`);
        return;
      }
      setError(e instanceof Error ? e.message : 'Failed to load portal.');
    } finally {
      if (isInitial) {
        setLoading(false);
        initialLoadDone.current = true;
      }
    }
  }, [router]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // Debounced refetch when the user types in the search box; backend now does
  // the field-spanning search so the result reflects every column (product,
  // metadata, doc number, etc.).
  useEffect(() => {
    const handle = window.setTimeout(() => {
      void loadAll(search);
    }, 300);
    return () => window.clearTimeout(handle);
    // loadAll is stable via useCallback; we intentionally exclude it from deps
    // so the debounce timer isn't reset on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const totals = useMemo(() => {
    const out: Record<PortalSubmissionKind, number> = {
      complaint: 0,
      stock_inquiry: 0,
      purchase_request: 0,
      sponsorship_form: 0,
    };
    for (const t of TYPES) out[t] = submissions[t]?.length ?? 0;
    return out;
  }, [submissions]);

  const handleLogout = useCallback(() => {
    const t = readPortalToken();
    clearPortalToken();
    const qs = new URLSearchParams({ reason: 'logout' });
    if (t) qs.set('token', t);
    router.replace(`/portal/verify?${qs.toString()}`);
  }, [router]);

  if (loading) {
    return (
      <div className="w-full px-3 pt-4 pb-4 space-y-3">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full px-3 pt-4 pb-4 space-y-3">
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
        <Button variant="outline" onClick={() => router.replace('/portal/verify')}>
          Verify with OTP
        </Button>
      </div>
    );
  }

  return (
    <div className="w-full px-3 pt-3 pb-4 space-y-3">
      {/* Header — Welcome centered, Log out anchored to top-right. */}
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

      {/* Search input + status-filter icon button on the same row to save
          vertical space. The button gets a primary outline when a non-default
          filter is active. */}
      <div className="flex items-stretch gap-2">
        <Input
          variant="lg"
          type="search"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-12 text-base flex-1"
          aria-label="Search submissions"
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="outline"
              className={`h-12 w-12 p-0 shrink-0 ${
                statusFilter !== 'all' ? 'border-primary text-primary' : ''
              }`}
              aria-label="Filter by status"
              title={
                statusFilter === 'all'
                  ? 'Filter by status'
                  : `Filter: ${statusFilter}`
              }
            >
              <Filter className="h-5 w-5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[10rem]">
            <DropdownMenuRadioGroup
              value={statusFilter}
              onValueChange={(v) => setStatusFilter(v as StatusFilter)}
            >
              <DropdownMenuRadioItem value="all">All statuses</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="draft">Draft</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="submitted">Submitted</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="rejected">Rejected</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex items-stretch gap-2">
        <Select
          value={activeTab}
          onValueChange={(v) => handleTabChange(v as PortalSubmissionKind)}
        >
          <SelectTrigger
            size="lg"
            className="flex-1 h-12 text-base"
            aria-label="Submission type"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                <span className="flex items-center gap-2">
                  {SUBMISSION_LABELS[t]}
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
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant="outline"
          onClick={handleSetDefaultTab}
          disabled={!contact || savedDefaultTab === activeTab}
          aria-label={
            savedDefaultTab === activeTab
              ? `${SUBMISSION_LABELS[activeTab]} is your default tab`
              : `Set ${SUBMISSION_LABELS[activeTab]} as default tab`
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
              savedDefaultTab === activeTab ? 'fill-yellow-400 text-yellow-500' : ''
            }`}
          />
        </Button>
      </div>

      <SubmissionList
        kind={activeTab}
        items={submissions[activeTab] ?? []}
        statusFilter={statusFilter}
      />
    </div>
  );
}

function SubmissionList({
  kind,
  items,
  statusFilter,
}: {
  kind: PortalSubmissionKind;
  items: PortalSubmissionSummary[];
  statusFilter: StatusFilter;
}) {
  const filtered = useMemo(() => {
    // Substring search runs server-side (every field). Local filter only
    // narrows by status for a snappy tab switch.
    if (statusFilter === 'all') return items;
    return items.filter((r) => effectiveStatus(r) === statusFilter);
  }, [items, statusFilter]);

  const [previewRow, setPreviewRow] = useState<PortalSubmissionSummary | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button asChild className="h-10">
          <Link href={`/portal/${kind}/new`}>
            <Plus className="h-4 w-4 mr-2" />
            New {SUBMISSION_LABELS[kind]}
          </Link>
        </Button>
      </div>
      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground space-y-2">
            <FileText className="h-8 w-8 mx-auto" />
            {items.length === 0 ? (
              <p>No {SUBMISSION_LABELS[kind].toLowerCase()} submissions yet.</p>
            ) : (
              <p>No submissions match your filters.</p>
            )}
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {filtered.map((row) => (
            <li key={row.id}>
              <SubmissionCard
                row={row}
                kind={kind}
                onLongPress={() => setPreviewRow(row)}
              />
            </li>
          ))}
        </ul>
      )}

      <SubmissionPreviewDialog
        row={previewRow}
        kind={kind}
        onOpenChange={(open) => !open && setPreviewRow(null)}
      />
    </div>
  );
}

function SubmissionCard({
  row,
  kind,
  onLongPress,
}: {
  row: PortalSubmissionSummary;
  kind: PortalSubmissionKind;
  onLongPress: () => void;
}) {
  const router = useRouter();
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);
  const meta = pickCardMeta(row);
  const primary = row.document_number ?? row.title ?? '—';
  const tintClass = statusCardClass(row);

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

  const statusText = row.is_draft ? 'Draft' : statusLabel(row.status);

  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => {
        if (longPressFired.current) {
          longPressFired.current = false;
          return;
        }
        router.push(`/portal/${kind}/${row.id}`);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          router.push(`/portal/${kind}/${row.id}`);
        }
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        onLongPress();
      }}
      onTouchStart={startPress}
      onTouchEnd={clearPress}
      onTouchMove={clearPress}
      onTouchCancel={clearPress}
      onMouseDown={startPress}
      onMouseUp={clearPress}
      onMouseLeave={clearPress}
      className={`relative block rounded-lg border ${tintClass} px-3.5 py-3 pr-3 hover:brightness-95 active:brightness-90 transition select-none cursor-pointer`}
    >
      {/* Status badge anchored top-right; allows multi-word status to wrap
          onto two lines without colliding with the primary text. */}
      <Badge
        variant={statusVariant(row)}
        className="absolute top-2 right-2 max-w-[45%] whitespace-normal text-right leading-tight justify-end"
      >
        {statusText}
      </Badge>
      <div className="space-y-1 pr-[45%]">
        <p className="text-base font-semibold break-words" title={primary}>
          {primary}
        </p>
      </div>
      <div className="space-y-1 mt-1">
        {meta.product && (
          <p className="text-sm text-foreground/80 break-words" title={meta.product}>
            <span className="text-muted-foreground">Product: </span>
            {meta.product}
          </p>
        )}
        {meta.project && (
          <p className="text-sm text-foreground/80 break-words" title={meta.project}>
            <span className="text-muted-foreground">Project: </span>
            {meta.project}
          </p>
        )}
        {meta.customer && (
          <p className="text-sm text-foreground/80 break-words" title={meta.customer}>
            <span className="text-muted-foreground">Customer: </span>
            {meta.customer}
          </p>
        )}
        {row.created_at && (
          <p className="text-xs text-muted-foreground">
            {new Date(row.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}
          </p>
        )}
        {row.rejection_reason && (
          <p className="text-xs text-destructive line-clamp-2">{row.rejection_reason}</p>
        )}
      </div>
    </div>
  );
}

function SubmissionPreviewDialog({
  row,
  kind,
  onOpenChange,
}: {
  row: PortalSubmissionSummary | null;
  kind: PortalSubmissionKind;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const meta = row ? pickCardMeta(row) : { product: undefined, project: undefined, customer: undefined };
  const entries: { label: string; value: string }[] = [];
  if (row) {
    if (row.document_number) entries.push({ label: 'Document number', value: row.document_number });
    if (row.title) entries.push({ label: 'Title', value: row.title });
    if (meta.product) entries.push({ label: 'Product', value: meta.product });
    if (meta.project) entries.push({ label: 'Project', value: meta.project });
    if (meta.customer) entries.push({ label: 'Customer', value: meta.customer });
    if (row.delivery_order_number) entries.push({ label: 'DO number', value: row.delivery_order_number });
    if (row.item_description) entries.push({ label: 'Item description', value: row.item_description });
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
    if (row.rejection_reason) entries.push({ label: 'Rejection reason', value: row.rejection_reason });
  }

  return (
    <Dialog open={Boolean(row)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2 flex-wrap">
            <span className="break-words">
              {row?.document_number ?? row?.title ?? 'Submission'}
            </span>
            {row && (
              <Badge variant={statusVariant(row)}>
                {row.is_draft ? 'Draft' : statusLabel(row.status)}
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 min-h-0 overflow-y-auto space-y-3 -mx-1 px-1">
          {entries.map((e) => (
            <div key={e.label} className="space-y-0.5">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {e.label}
              </p>
              <p className="text-sm break-words whitespace-pre-wrap">{e.value}</p>
            </div>
          ))}
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="h-10">
            Close
          </Button>
          <Button
            onClick={() => {
              if (row) router.push(`/portal/${kind}/${row.id}`);
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

export default function PortalPage() {
  return (
    <Suspense fallback={null}>
      <PortalLandingContent />
    </Suspense>
  );
}

