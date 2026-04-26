'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { toast } from 'sonner';
import { Mail } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { ActivityMessageComposer, type ActivityUserOption } from './ActivityMessageComposer';
import {
  listMasterQuotationTaskConversationMessages,
  listProjectTaskConversationMessages,
  postMasterQuotationTaskConversationMessage,
  postProjectTaskConversationMessage,
  type ConversationMessage,
  type ConversationScope,
} from '../services/entityConversationApi';

function formatMsgTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function messagePlainText(html: string): string {
  if (typeof window === 'undefined') {
    return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  }
  const d = document.createElement('div');
  d.innerHTML = html || '';
  return (d.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function MessageBubble({
  msg,
  currentUserId,
}: {
  msg: ConversationMessage;
  currentUserId?: string | null;
}) {
  const mine = msg.author?.id === currentUserId;
  return (
    <div
      className={cn(
        'rounded-xl border px-3 py-2 text-sm shadow-sm',
        msg.is_system && 'border-dashed bg-muted/40',
        !msg.is_system && mine && 'border-sky-200 bg-sky-50/80',
        !msg.is_system && !mine && 'border-[#e5e7eb] bg-white',
      )}
    >
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-[#6a7282]">
        {msg.is_system ? (
          <Badge variant="secondary" className="font-normal">
            System
          </Badge>
        ) : (
          <>
            <span className="font-medium text-[#101828]">
              {(msg.author?.name || '').trim() || msg.author?.email || 'User'}
              {mine ? ' (you)' : ''}
            </span>
          </>
        )}
        <span className="tabular-nums">{formatMsgTime(msg.created_at)}</span>
      </div>
      <div
        className="prose prose-sm max-w-none text-[#364153] [&_.mention]:font-medium [&_.mention]:text-[#1447e6] [&_a[href^='mention:']]:font-medium [&_a[href^='mention:']]:text-[#1447e6] [&_a[href^='mention:']]:no-underline [&_p]:my-1"
        dangerouslySetInnerHTML={{ __html: msg.body_html || '' }}
      />
    </div>
  );
}

export type TaskActivitiesButtonProps = {
  variant: 'project_task' | 'master_quotation_task';
  parentId: string;
  taskId: string;
  taskTitle: string;
  canPost: boolean;
  /** Optional: hide when parent context missing */
  disabled?: boolean;
};

/** Mail icon opens task-scoped activities in an anchored popover (distinct from document-level sheet dock). */
export function TaskActivitiesButton({
  variant,
  parentId,
  taskId,
  taskTitle,
  canPost,
  disabled,
}: TaskActivitiesButtonProps) {
  const { data: session } = useSession();
  const uid = session?.user?.id;
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [panelTab, setPanelTab] = useState<'activities' | 'internal'>('activities');
  const scope: ConversationScope = panelTab === 'activities' ? 'activity' : 'internal_note';

  const { data: users = [] } = useQuery({
    queryKey: ['user-select-task-activities'],
    queryFn: async () => {
      const r = await apiFetch('/api/user-management/users/select');
      if (!r.ok) return [] as ActivityUserOption[];
      const raw = await r.json();
      const arr = Array.isArray(raw) ? raw : (raw as { data?: unknown })?.data;
      if (!Array.isArray(arr)) return [];
      return arr.map((x: unknown) => {
        const o = x as Record<string, unknown>;
        return {
          id: String(o.id ?? ''),
          name: (o.name as string) ?? null,
          email: String(o.email ?? ''),
        };
      }).filter((u) => u.id);
    },
    staleTime: 60_000,
  });

  const {
    data: messages = [],
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['entity-conversation-task', variant, parentId, taskId, scope],
    queryFn: async () => {
      if (variant === 'project_task') {
        return listProjectTaskConversationMessages(parentId, taskId, { scope });
      }
      return listMasterQuotationTaskConversationMessages(parentId, taskId, { scope });
    },
    enabled: open && !!parentId && !!taskId,
  });

  const sortedMessages = useMemo(() => [...messages].sort((a, b) => a.created_at.localeCompare(b.created_at)), [messages]);

  const filteredMessages = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return sortedMessages;
    return sortedMessages.filter((m) => {
      const blob = [
        messagePlainText(m.body_html || ''),
        (m.author?.name || '').toLowerCase(),
        (m.author?.email || '').toLowerCase(),
        m.is_system ? 'system' : '',
      ].join(' ');
      return blob.includes(q);
    });
  }, [sortedMessages, searchQuery]);

  const sendMessage = async (bodyHtml: string) => {
    try {
      if (variant === 'project_task') {
        await postProjectTaskConversationMessage(parentId, taskId, { scope, body_html: bodyHtml });
      } else {
        await postMasterQuotationTaskConversationMessage(parentId, taskId, { scope, body_html: bodyHtml });
      }
      toast.success(panelTab === 'activities' ? 'Posted.' : 'Saved.');
      await refetch();
    } catch {
      toast.error('Could not save message.');
    }
  };

  const attachmentEntity =
    variant === 'project_task'
      ? { entityType: 'commercial_project', entityId: parentId }
      : { entityType: 'commercial_master_quotation', entityId: parentId };

  const panelInner = (
    <Tabs
      value={panelTab}
      onValueChange={(v) => {
        setPanelTab(v as 'activities' | 'internal');
        setSearchQuery('');
      }}
      className="flex min-h-0 flex-1 flex-col"
    >
      <TabsList className="mx-3 mt-3 grid h-auto w-auto grid-cols-2 rounded-lg bg-muted/50 p-1">
        <TabsTrigger value="activities" className="rounded-md">
          Activities
        </TabsTrigger>
        <TabsTrigger value="internal" className="rounded-md">
          Internal notes
        </TabsTrigger>
      </TabsList>

      <div className="px-3 pt-2">
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search messages…"
          className="h-9 text-sm"
          aria-label="Search in this thread"
        />
      </div>

      <TabsContent value="activities" className="mt-0 flex min-h-0 flex-1 flex-col px-0 pb-0 data-[state=inactive]:hidden">
        <ScrollArea className="min-h-0 flex-1 px-3">
          <div className="flex flex-col gap-3 py-2 pe-2">
            {isFetching ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : filteredMessages.length === 0 ? (
              <p className="text-muted-foreground py-6 text-center text-sm">
                {sortedMessages.length === 0 ? 'No activity yet.' : 'No matches.'}
              </p>
            ) : (
              filteredMessages.map((m) => <MessageBubble key={m.id} msg={m} currentUserId={uid} />)
            )}
          </div>
        </ScrollArea>
        <div className="border-t border-[#e5e7eb] bg-[#fafafa] p-3">
          {canPost ? (
            <ActivityMessageComposer
              users={users}
              onSend={sendMessage}
              placeholder="Share an update… Use @ to mention someone."
              attachmentContext={attachmentEntity}
            />
          ) : (
            <p className="text-muted-foreground text-sm">You don&apos;t have permission to post.</p>
          )}
        </div>
      </TabsContent>

      <TabsContent value="internal" className="mt-0 flex min-h-0 flex-1 flex-col px-0 pb-0 data-[state=inactive]:hidden">
        <ScrollArea className="min-h-0 flex-1 px-3">
          <div className="flex flex-col gap-3 py-2 pe-2">
            {isFetching ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : filteredMessages.length === 0 ? (
              <p className="text-muted-foreground py-6 text-center text-sm">
                {sortedMessages.length === 0 ? 'No internal notes yet.' : 'No matches.'}
              </p>
            ) : (
              filteredMessages.map((m) => <MessageBubble key={m.id} msg={m} currentUserId={uid} />)
            )}
          </div>
        </ScrollArea>
        <div className="border-t border-[#e5e7eb] bg-[#fafafa] p-3">
          {canPost ? (
            <ActivityMessageComposer
              users={users}
              onSend={sendMessage}
              placeholder="Private notes (only you can see these)…"
              attachmentContext={attachmentEntity}
            />
          ) : (
            <p className="text-muted-foreground text-sm">You don&apos;t have permission to edit.</p>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 shrink-0 text-[#e7000b]"
          aria-label={`Open activities for task ${taskTitle || taskId}`}
          aria-expanded={open}
          disabled={disabled}
          onClick={(e) => e.stopPropagation()}
        >
          <Mail className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        sideOffset={6}
        collisionPadding={12}
        className="flex w-[min(440px,calc(100vw-1.5rem))] max-w-[440px] flex-col overflow-hidden p-0 shadow-lg"
        onOpenAutoFocus={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-[#e5e7eb] px-4 py-3">
          <p className="text-base font-semibold text-[#101828]">Task activities</p>
          <p className="truncate text-sm text-[#364153]" title={taskTitle}>
            {taskTitle?.trim() ? taskTitle : 'Untitled task'}
          </p>
        </div>
        <div className="flex h-[min(78vh,560px)] min-h-0 flex-col">{panelInner}</div>
      </PopoverContent>
    </Popover>
  );
}
