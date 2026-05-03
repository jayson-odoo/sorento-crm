'use client';

import { useEffect, useState } from 'react';
import { Activity, FileText, MessageSquare } from 'lucide-react';
import { toast } from 'sonner';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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

function relativeTime(iso: string): string {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleString();
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
        p.note ? ` — ${p.note as string}` : ''
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
          className="fixed right-4 bottom-4 z-30 size-12 rounded-full shadow-xl bg-red-600 hover:bg-red-700 animate-pulse"
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
            <TabsList className="grid grid-cols-3 w-full">
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
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center pt-4">No activity yet.</p>
        ) : (
          items.map((it) => (
            <div key={it.id} className="bg-muted/30 border rounded-md p-3">
              <div className="flex items-center gap-2 mb-1">
                {it.kind === 'system' ? (
                  <Badge variant="secondary">System</Badge>
                ) : (
                  <>
                    <Avatar className="size-6">
                      <AvatarImage src={it.actor?.avatar_url ?? undefined} />
                      <AvatarFallback>
                        {(it.actor?.name ?? '?').charAt(0).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-sm font-medium">{it.actor?.name ?? 'Unknown'}</span>
                  </>
                )}
                <span className="ms-auto text-xs text-muted-foreground">
                  {relativeTime(it.created_at)}
                </span>
              </div>
              {it.kind === 'system' ? (
                <p className="text-sm">
                  {formatSystemEvent(it.system_template, it.system_payload)}
                </p>
              ) : (
                <div className="text-sm whitespace-pre-wrap">
                  {it.body_text ?? ''}
                </div>
              )}
            </div>
          ))
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
                <span className="text-xs text-muted-foreground">{relativeTime(n.created_at)}</span>
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
        <Select value={contactId} onValueChange={setContactId} disabled={contacts.length === 0}>
          <SelectTrigger>
            <SelectValue
              placeholder={contacts.length === 0 ? 'No contacts linked' : 'Choose a contact'}
            />
          </SelectTrigger>
          <SelectContent>
            {contacts.map((c) => (
              <SelectItem key={c.contact_id} value={c.contact_id}>
                {c.name ?? c.phone ?? c.contact_id}
                {c.is_primary ? ' (primary)' : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
              <div className="text-[10px] opacity-70 mt-1">{relativeTime(m.sent_at)}</div>
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
