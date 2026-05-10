'use client';

import { use, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { CheckCircle2, AlertTriangle } from 'lucide-react';
import type { Ticket } from '@/app/(protected)/ticket-management/tickets/types/ticket.types';

interface PageProps {
  params: Promise<{ token: string }>;
}

export default function TicketDraftPortalPage({ params }: PageProps) {
  const { token } = use(params);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    fetch(`/api/v1/public/ticket-drafts/${encodeURIComponent(token)}`)
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || 'Failed to load draft');
        }
        return r.json();
      })
      .then((data) => {
        if (!cancel) setTicket(data);
      })
      .catch((e: Error) => {
        if (!cancel) setError(e.message);
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });
    return () => {
      cancel = true;
    };
  }, [token]);

  async function submitDraft() {
    setBusy(true);
    try {
      const r = await fetch(
        `/api/v1/public/ticket-drafts/${encodeURIComponent(token)}/submit`,
        { method: 'POST' },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || 'Submit failed');
      }
      const updated = await r.json();
      setTicket(updated);
      setSubmitted(true);
      toast.success('Ticket submitted to IT admin');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelDraft() {
    if (!window.confirm('Cancel this draft? This cannot be undone.')) return;
    setBusy(true);
    try {
      const r = await fetch(
        `/api/v1/public/ticket-drafts/${encodeURIComponent(token)}/cancel`,
        { method: 'POST' },
      );
      if (!r.ok && r.status !== 204) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || 'Cancel failed');
      }
      setCancelled(true);
      toast.success('Draft cancelled');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-4">
        <Skeleton className="h-8 w-64 mb-4" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error || !ticket) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-4">
        <Alert variant="destructive">
          <AlertIcon><AlertTriangle /></AlertIcon>
          <AlertTitle>{error || 'Could not load this draft.'}</AlertTitle>
        </Alert>
      </div>
    );
  }

  if (cancelled) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-4 text-center">
        <h1 className="text-2xl font-semibold mb-2">Draft cancelled</h1>
        <p className="text-muted-foreground">No ticket was created. You can close this page.</p>
      </div>
    );
  }

  const isDraft = ticket.status === 'draft';

  return (
    <div className="max-w-2xl mx-auto py-12 px-4">
      <h1 className="text-2xl font-semibold mb-2">IT Support Ticket</h1>
      <p className="text-muted-foreground mb-6">
        Review the details below. Click <strong>Submit to IT admin</strong> when ready.
      </p>

      {submitted && (
        <Alert variant="success" className="mb-6">
          <AlertIcon><CheckCircle2 /></AlertIcon>
          <AlertTitle>
            Ticket {ticket.ticket_number ?? ticket.id.slice(0, 8)} submitted. Our IT team will follow up shortly.
          </AlertTitle>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {ticket.title}
            <Badge variant="secondary" className="capitalize">
              {ticket.priority}
            </Badge>
            <Badge variant="outline" className="capitalize">
              {ticket.category}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {ticket.description_html ? (
            <div
              className="prose prose-sm max-w-none"
              dangerouslySetInnerHTML={{ __html: ticket.description_html }}
            />
          ) : (
            <p className="text-sm whitespace-pre-wrap">{ticket.description_text ?? '—'}</p>
          )}
        </CardContent>
      </Card>

      {isDraft && !submitted && (
        <div className="flex gap-2 justify-end mt-6">
          <Button variant="outline" onClick={cancelDraft} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submitDraft} disabled={busy}>
            Submit to IT admin
          </Button>
        </div>
      )}

      {!isDraft && !submitted && (
        <Alert className="mt-6">
          <AlertIcon><CheckCircle2 /></AlertIcon>
          <AlertTitle>
            This ticket is already {ticket.status}. The IT team is on it.
          </AlertTitle>
        </Alert>
      )}
    </div>
  );
}
