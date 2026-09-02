'use client';

import { useEffect, useState } from 'react';
import { Activity, FileText, MessageSquare } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { EventTimeline } from '@/components/common/EventTimeline';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  deleteNote,
  listActivities,
  listEntityContacts,
  listMessages,
  listNotes,
  postActivity,
  postNote,
  sendMessage,
} from './activitiesPanelService';
import type {
  ActivityEvent,
  EntityMessage,
  EntityRespondContact,
  InternalNote,
  PanelTab,
} from './types';

/** Absolute, per ADR 1d: a relative stamp rots while the page is open and cannot be quoted. */
function stampedAt(iso: string): string {
  return formatDateTimeInMalaysia(iso);
}

function formatSystemEvent(
  template: string | null | undefined,
  payload: Record<string, unknown> | null | undefined,
): string {
  const t = template ?? '';
  const p = payload ?? {};
  switch (t) {
    case 'entity.created':
      return `Ticket ${(p.ticket_number as string) ?? ''} was created.`;
    case 'status.changed':
      return `Status changed: ${(p.from as string) ?? '?'} → ${(p.to as string) ?? '?'}${
        p.note ? ` - ${p.note as string}` : ''
      }`;
    case 'assignee.changed':
      return `Assignee changed.`;
    case 'response.updated':
      return p.first_response ? 'First response posted.' : 'Response updated.';
    case 'resolution.updated':
      return 'Resolution updated.';
    case 'watchers.added':
      return 'Watchers added.';
    case 'watchers.removed':
      return 'Watcher removed.';
    case 'message.sent':
      return 'Outbound message sent.';
    default:
      return t || 'System event';
  }
}

interface Props {
  entityType: string;
  entityId: string;
}

export default function ActivitiesNotesPanel({ entityType, entityId }: Props) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<PanelTab>('activities');

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="primary"
          size="icon"
          className="fixed end-12 bottom-4 z-30 size-12 rounded-full shadow-xl bg-red-600 hover:bg-red-700 animate-pulse"
          aria-label="Open activities & notes"
        >
          <Activity className="size-5 text-white" />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[420px] flex flex-col p-0"
      >
        <SheetHeader className="p-5 border-b">
          <SheetTitle>Activities &amp; notes</SheetTitle>
          <SheetDescription className="text-sm">
            Activities are visible to everyone with access. Internal notes are private to you.
          </SheetDescription>
        </SheetHeader>
        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as PanelTab)}
          className="flex-1 flex flex-col overflow-hidden"
        >
          <div className="px-3 pt-3">
            <TabsList variant="default" className="w-full">
              <TabsTrigger value="activities" aria-label="Activities">
                <Activity className="size-4" />
              </TabsTrigger>
              <TabsTrigger value="notes" aria-label="Internal notes">
                <FileText className="size-4" />
              </TabsTrigger>
              <TabsTrigger value="messages" aria-label="Messages">
                <MessageSquare className="size-4" />
              </TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="activities" className="flex-1 flex flex-col overflow-hidden m-0">
            <ActivitiesTab entityType={entityType} entityId={entityId} active={open && tab === 'activities'} />
          </TabsContent>
          <TabsContent value="notes" className="flex-1 flex flex-col overflow-hidden m-0">
            <NotesTab entityType={entityType} entityId={entityId} active={open && tab === 'notes'} />
          </TabsContent>
          <TabsContent value="messages" className="flex-1 flex flex-col overflow-hidden m-0">
            <MessagesTab entityType={entityType} entityId={entityId} active={open && tab === 'messages'} />
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}

// --------- Activities tab ---------

function ActivitiesTab({
  entityType,
  entityId,
  active,
}: {
  entityType: string;
  entityId: string;
  active: boolean;
}) {
  const [items, setItems] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const res = await listActivities(entityType, entityId, { limit: 50 });
      setItems(res.items);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (active) void reload();
     
  }, [active, entityType, entityId]);

  async function submit() {
    if (!draft.trim()) return;
    setPosting(true);
    try {
      await postActivity(entityType, entityId, {
        body_html: `<p>${draft.replace(/\n/g, '<br>')}</p>`,
        body_text: draft,
      });
      setDraft('');
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setPosting(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          // A history reads as a timeline, not a stack of cards: one rail, grouped by day,
          // with absolute times. See components/common/EventTimeline.
          <EventTimeline
            events={items.map((it, index) => ({
              id: it.id,
              title:
                it.kind === 'system'
                  ? formatSystemEvent(it.system_template, it.system_payload)
                  : (it.actor?.name ?? 'Unknown'),
              at: it.created_at,
              tone: index === 0 ? 'current' : it.kind === 'system' ? 'muted' : 'default',
              marker:
                it.kind === 'system' ? undefined : (
                  <Avatar className="size-5">
                    <AvatarImage src={it.actor?.avatar_url ?? undefined} />
                    <AvatarFallback className="text-[10px]">
                      {(it.actor?.name ?? '?').charAt(0).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                ),
              tags:
                it.kind === 'system' ? (
                  <Badge variant="secondary" appearance="light" className="text-[11px]">
                    System
                  </Badge>
                ) : null,
              detail:
                it.kind === 'system' ? null : (
                  <span className="whitespace-pre-wrap">{it.body_text ?? ''}</span>
                ),
            }))}
            emptyTitle="No activity yet"
          />
        )}
      </div>
      <div className="border-t p-3 space-y-2">
        <Textarea
          placeholder="Share an update…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
        />
        <div className="flex justify-end">
          <Button size="sm" disabled={!draft.trim() || posting} onClick={submit}>
            {posting ? 'Posting…' : 'Post'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// --------- Notes tab ---------

function NotesTab({
  entityType,
  entityId,
  active,
}: {
  entityType: string;
  entityId: string;
  active: boolean;
}) {
  const [items, setItems] = useState<InternalNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const res = await listNotes(entityType, entityId, { limit: 50 });
      setItems(res.items);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (active) void reload();
     
  }, [active, entityType, entityId]);

  async function submit() {
    if (!draft.trim()) return;
    setPosting(true);
    try {
      await postNote(entityType, entityId, {
        body_html: `<p>${draft.replace(/\n/g, '<br>')}</p>`,
        body_text: draft,
      });
      setDraft('');
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setPosting(false);
    }
  }

  async function remove(noteId: string) {
    try {
      await deleteNote(noteId);
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading ? (
          <Skeleton className="h-20 w-full" />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center pt-4">No internal notes yet.</p>
        ) : (
          items.map((n) => (
            <div key={n.id} className="bg-muted/30 border rounded-md p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs text-muted-foreground">{stampedAt(n.created_at)}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ms-auto h-6 px-2 text-xs"
                  onClick={() => remove(n.id)}
                >
                  Delete
                </Button>
              </div>
              <div className="text-sm whitespace-pre-wrap">{n.body_text ?? ''}</div>
            </div>
          ))
        )}
      </div>
      <div className="border-t p-3 space-y-2">
        <Textarea
          placeholder="Private notes (only you can see these)…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
        />
        <div className="flex justify-end">
          <Button size="sm" disabled={!draft.trim() || posting} onClick={submit}>
            {posting ? 'Saving…' : 'Save note'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// --------- Messages tab ---------

function MessagesTab({
  entityType,
  entityId,
  active,
}: {
  entityType: string;
  entityId: string;
  active: boolean;
}) {
  const [contacts, setContacts] = useState<EntityRespondContact[]>([]);
  const [contactId, setContactId] = useState<string>('');
  const [items, setItems] = useState<EntityMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!active) return;
    listEntityContacts(entityType, entityId)
      .then((cs) => {
        setContacts(cs);
        const primary = cs.find((c) => c.is_primary) ?? cs[0];
        if (primary) setContactId(primary.contact_id);
      })
      .catch((e: Error) => toast.error(e.message));
  }, [active, entityType, entityId]);

  useEffect(() => {
    if (!contactId) return;
    setLoading(true);
    listMessages(entityType, entityId, { contact_id: contactId })
      .then((res) => setItems(res.items))
      .catch((e: Error) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, [contactId, entityType, entityId]);

  async function send() {
    if (!contactId || !draft.trim()) return;
    setSending(true);
    try {
      await sendMessage(entityType, entityId, { contact_id: contactId, body: draft });
      setDraft('');
      toast.success('Message queued');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="p-3 border-b">
        <SearchableSelect
          value={contactId}
          onChange={setContactId}
          disabled={contacts.length === 0}
          options={contacts.map((c) => ({
            value: c.contact_id,
            label: `${c.name ?? c.phone ?? c.contact_id}${c.is_primary ? ' (primary)' : ''}`,
          }))}
          placeholder={contacts.length === 0 ? 'No contacts linked' : 'Choose a contact'}
        />
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {!contactId ? (
          <p className="text-sm text-muted-foreground text-center pt-4">
            Choose a contact to view conversation.
          </p>
        ) : loading ? (
          <Skeleton className="h-20 w-full" />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center pt-4">
            No messages yet for this contact.
          </p>
        ) : (
          items.map((m) => (
            <div
              key={m.id}
              className={
                m.direction === 'outgoing'
                  ? 'ms-auto max-w-[80%] bg-primary text-primary-foreground rounded-md p-2 text-sm'
                  : 'me-auto max-w-[80%] bg-muted rounded-md p-2 text-sm'
              }
            >
              {m.body ?? ''}
              <div className="text-[10px] opacity-70 mt-1">{stampedAt(m.sent_at)}</div>
            </div>
          ))
        )}
      </div>
      <div className="border-t p-3 space-y-2">
        <Textarea
          placeholder={contactId ? 'Type a reply…' : 'Choose a contact to reply.'}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          disabled={!contactId}
        />
        <div className="flex justify-end">
          <Button size="sm" disabled={!contactId || !draft.trim() || sending} onClick={send}>
            {sending ? 'Sending…' : 'Send'}
          </Button>
        </div>
      </div>
    </div>
  );
}
