'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, ChevronRight, FileText, Plus } from 'lucide-react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  PortalContact,
  PortalSubmissionKind,
  PortalSubmissionSummary,
  PortalUnauthorizedError,
  SUBMISSION_LABELS,
  fetchMe,
  fetchSubmissions,
  readPortalToken,
  writePortalToken,
} from './lib/portal-client';

const TYPES: PortalSubmissionKind[] = [
  'stock_inquiry',
  'complaint',
  'purchase_request',
  'sponsorship_form',
];

function statusVariant(status: string): 'primary' | 'secondary' | 'destructive' | 'success' | 'warning' {
  if (status === 'rejected') return 'destructive';
  if (status === 'draft') return 'warning';
  if (status === 'approved' || status === 'completed') return 'success';
  return 'secondary';
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
    if (!readPortalToken()) {
      router.replace('/portal/verify');
      return;
    }
    setLoading(true);
    try {
      const me = await fetchMe();
      setContact(me);
      const lists = await Promise.all(TYPES.map((t) => fetchSubmissions(t)));
      setSubmissions({
        stock_inquiry: lists[0],
        complaint: lists[1],
        purchase_request: lists[2],
        sponsorship_form: lists[3],
      });
      setError(null);
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        router.replace('/portal/verify?reason=expired');
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
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Welcome{contact?.name ? `, ${contact.name}` : ''}</CardTitle>
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

      <Tabs defaultValue="stock_inquiry">
        <TabsList className="flex flex-wrap gap-2">
          {TYPES.map((t) => (
            <TabsTrigger key={t} value={t} className="gap-2">
              {SUBMISSION_LABELS[t]}
              <Badge variant="secondary">{totals[t]}</Badge>
            </TabsTrigger>
          ))}
        </TabsList>
        {TYPES.map((t) => (
          <TabsContent key={t} value={t} className="mt-4">
            <SubmissionList kind={t} items={submissions[t] ?? []} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

function SubmissionList({ kind, items }: { kind: PortalSubmissionKind; items: PortalSubmissionSummary[] }) {
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
      {items.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground space-y-2">
            <FileText className="h-8 w-8 mx-auto" />
            <p>No {SUBMISSION_LABELS[kind].toLowerCase()} submissions yet.</p>
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {items.map((row) => (
            <li key={row.id}>
              <Link
                href={`/portal/${kind}/${row.id}`}
                className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-3 hover:bg-accent transition"
              >
                <div className="min-w-0 space-y-1">
                  <p className="truncate text-sm font-medium" title={row.title}>
                    {row.title}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {row.reference && <span>{row.reference}</span>}
                    {row.created_at && (
                      <span>
                        {new Date(row.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}
                      </span>
                    )}
                  </div>
                  {row.rejection_reason && (
                    <p className="text-xs text-destructive line-clamp-2">{row.rejection_reason}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant={statusVariant(row.is_draft ? 'draft' : row.status)}>
                    {row.is_draft ? 'Draft' : row.status}
                  </Badge>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </Link>
            </li>
          ))}
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
