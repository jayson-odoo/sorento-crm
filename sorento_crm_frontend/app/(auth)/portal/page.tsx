'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, ChevronRight, FileText, LogOut, Plus } from 'lucide-react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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

function statusVariant(status: string): 'primary' | 'secondary' | 'destructive' | 'success' | 'warning' {
  if (status === 'rejected') return 'destructive';
  if (status === 'draft') return 'warning';
  if (status === 'approved' || status === 'completed') return 'success';
  return 'secondary';
}

function effectiveStatus(row: PortalSubmissionSummary): StatusFilter {
  if (row.is_draft) return 'draft';
  if (row.status === 'rejected') return 'rejected';
  return 'submitted';
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

  // Pull token from URL on first load and persist to sessionStorage so reloads
  // (and child pages) don't need to keep it in the URL.
  useEffect(() => {
    const incoming = searchParams?.get('token');
    if (incoming) {
      writePortalToken(incoming);
      const url = new URL(window.location.href);
      url.searchParams.delete('token');
      router.replace(url.pathname + (url.search ? url.search : ''));
    }
  }, [router, searchParams]);

  const loadAll = useCallback(async () => {
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
    setLoading(true);
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
      const lists = await Promise.all(TYPES.map((t) => fetchSubmissions(t)));
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
        // the contact/space pair via /token-info.
        const qs = new URLSearchParams({ reason: 'expired' });
        if (existing) qs.set('token', existing);
        router.replace(`/portal/verify?${qs.toString()}`);
        return;
      }
      setError(e instanceof Error ? e.message : 'Failed to load portal.');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

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
      <div className="min-h-screen max-w-4xl mx-auto px-4 py-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen max-w-4xl mx-auto px-4 py-6 space-y-4">
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
    <div className="min-h-screen max-w-4xl mx-auto px-4 py-6 space-y-6">
      <Card>
        <CardHeader className="pb-3 flex flex-row items-start justify-between gap-2">
          <CardTitle className="text-base">Welcome{contact?.name ? `, ${contact.name}` : ''}</CardTitle>
          <Button variant="outline" size="sm" onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" />
            Log out
          </Button>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1">
          {contact?.phone_number && <p>Phone: {contact.phone_number}</p>}
          {contact?.expires_at && (
            <p className="text-xs">
              This portal session expires{' '}
              {new Date(contact.expires_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}.
              You'll re-verify with an OTP afterwards.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-col sm:flex-row gap-2">
        <Input
          type="search"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1"
          aria-label="Search submissions"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-xs shadow-black/5 outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/30 sm:w-40"
          aria-label="Filter by status"
        >
          <option value="all">All statuses</option>
          <option value="draft">Draft</option>
          <option value="submitted">Submitted</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      <Tabs defaultValue="stock_inquiry">
        <TabsList className="flex flex-wrap gap-2 overflow-x-auto sm:flex-nowrap">
          {TYPES.map((t) => (
            <TabsTrigger key={t} value={t} className="gap-2 whitespace-nowrap">
              {SUBMISSION_LABELS[t]}
              <Badge variant="secondary">{totals[t]}</Badge>
            </TabsTrigger>
          ))}
        </TabsList>
        {TYPES.map((t) => (
          <TabsContent key={t} value={t} className="mt-4">
            <SubmissionList
              kind={t}
              items={submissions[t] ?? []}
              search={search}
              statusFilter={statusFilter}
            />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

function SubmissionList({
  kind,
  items,
  search,
  statusFilter,
}: {
  kind: PortalSubmissionKind;
  items: PortalSubmissionSummary[];
  search: string;
  statusFilter: StatusFilter;
}) {
  const filtered = useMemo(() => {
    let rows = items;
    // Apply status filter first (per spec).
    if (statusFilter !== 'all') {
      rows = rows.filter((r) => effectiveStatus(r) === statusFilter);
    }
    // Then substring search across visible-ish fields.
    const q = search.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) => {
        const created = r.created_at
          ? new Date(r.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })
          : '';
        const haystack = [
          r.document_number ?? '',
          r.title ?? '',
          r.status ?? '',
          r.reference ?? '',
          created,
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(q);
      });
    }
    return rows;
  }, [items, search, statusFilter]);

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button asChild size="sm">
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
        <ul className="space-y-2">
          {filtered.map((row) => {
            const primary = row.document_number ?? row.title;
            const showSecondary = Boolean(row.document_number && row.title);
            return (
              <li key={row.id}>
                <Link
                  href={`/portal/${kind}/${row.id}`}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-3 hover:bg-accent transition gap-3"
                >
                  <div className="min-w-0 space-y-1 flex-1">
                    <p className="truncate text-sm font-medium" title={primary}>
                      {primary}
                    </p>
                    {showSecondary && (
                      <p
                        className="truncate text-xs text-muted-foreground"
                        title={row.title}
                      >
                        {row.title}
                      </p>
                    )}
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {row.reference && <span>{row.reference}</span>}
                      {row.created_at && (
                        <span>
                          {new Date(row.created_at).toLocaleDateString(undefined, {
                            dateStyle: 'medium',
                          })}
                        </span>
                      )}
                    </div>
                    {row.rejection_reason && (
                      <p className="text-xs text-destructive line-clamp-2">
                        {row.rejection_reason}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant={statusVariant(row.is_draft ? 'draft' : row.status)}>
                      {row.is_draft ? 'Draft' : statusLabel(row.status)}
                    </Badge>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function PortalPage() {
  return (
    <Suspense fallback={null}>
      <PortalLandingContent />
    </Suspense>
  );
}
