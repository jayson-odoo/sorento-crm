'use client';

import { use, useEffect, useState } from 'react';
import { sanitizedHtml } from '@/lib/sanitize';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Textarea } from '@/components/ui/textarea';
import { CheckCircle2, AlertTriangle, Pencil } from 'lucide-react';
import type { Ticket } from '@/app/(protected)/ticket-management/tickets/types/ticket.types';
import RespondChatList from '@/components/common/RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

interface ConversationResponse {
  items: RespondMessageRenderable[];
  pagination?: { next?: string; previous?: string };
  error?: string;
  contact?: { name?: string | null; phone?: string | null } | null;
  source_message_id?: string | null;
}

interface PageProps {
  params: Promise<{ token: string }>;
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, '').trim();
}

export default function TicketDraftPortalPage({ params }: PageProps) {
  const { token } = use(params);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState('');
  const [conversation, setConversation] = useState<ConversationResponse | null>(null);
  const [conversationLoading, setConversationLoading] = useState(true);

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

  useEffect(() => {
    let cancel = false;
    setConversationLoading(true);
    fetch(`/api/v1/public/ticket-drafts/${encodeURIComponent(token)}/conversation?limit=50`)
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || 'Failed to load conversation');
        }
        return r.json() as Promise<ConversationResponse>;
      })
      .then((data) => {
        if (!cancel) setConversation(data);
      })
      .catch(() => {
        if (!cancel) setConversation({ items: [], error: 'Could not load chat history.' });
      })
      .finally(() => {
        if (!cancel) setConversationLoading(false);
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

  function startEdit() {
    if (!ticket) return;
    setDraftText(ticket.description_text ?? stripHtml(ticket.description_html ?? '') ?? '');
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setDraftText('');
  }

  async function saveEdit() {
    setBusy(true);
    try {
      const r = await fetch(
        `/api/v1/public/ticket-drafts/${encodeURIComponent(token)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description_text: draftText }),
        },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || 'Save failed');
      }
      const updated = await r.json();
      setTicket(updated);
      setEditing(false);
      toast.success('Description updated');
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

      <Card className="mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Chat history</CardTitle>
          <p className="text-xs text-muted-foreground">
            The highlighted message is what this draft was based on. Scroll to review the full conversation, then edit the description below if you want to add detail.
          </p>
        </CardHeader>
        <CardContent>
          {conversationLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-3/4" />
              <Skeleton className="h-12 w-2/3" />
            </div>
          ) : conversation && conversation.items.length > 0 ? (
            <RespondChatList
              items={conversation.items}
              contactName={conversation.contact?.name ?? null}
              contactPhone={conversation.contact?.phone ?? null}
              maxHeightClass="max-h-[50vh]"
              highlightMessageId={
                conversation.source_message_id ?? ticket.source_message_id ?? null
              }
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              {conversation?.error ?? 'No chat history available for this draft.'}
            </p>
          )}
        </CardContent>
      </Card>

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
            {isDraft && !submitted && !editing && (
              <Button
                variant="ghost"
                size="sm"
                className="ms-auto"
                onClick={startEdit}
                disabled={busy}
              >
                <Pencil className="size-4 me-1" />
                Edit
              </Button>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {editing ? (
            <div className="space-y-3">
              <Textarea
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                rows={6}
                placeholder="Describe the issue..."
                disabled={busy}
              />
              <div className="flex gap-2 justify-end">
                <Button variant="outline" size="sm" onClick={cancelEdit} disabled={busy}>
                  Cancel
                </Button>
                <Button size="sm" onClick={saveEdit} disabled={busy || !draftText.trim()}>
                  Save
                </Button>
              </div>
            </div>
          ) : ticket.description_html ? (
            <div
              className="prose prose-sm max-w-none"
              dangerouslySetInnerHTML={sanitizedHtml(ticket.description_html)}
            />
          ) : (
            <p className="text-sm whitespace-pre-wrap">{ticket.description_text ?? '—'}</p>
          )}
        </CardContent>
      </Card>

      {isDraft && !submitted && !editing && (
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
