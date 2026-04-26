'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { toast } from 'sonner';
import { Activity, MessageSquare, StickyNote } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { ActivityMessageComposer, type ActivityUserOption } from './ActivityMessageComposer';
import { useEntityActivitiesDock, type EntityActivitiesDockRegistration } from './entityActivitiesDockContext';
import {
  listLeadConversationMessages,
  listMasterQuotationConversationMessages,
  listProjectConversationMessages,
  postLeadConversationMessage,
  postMasterQuotationConversationMessage,
  postProjectConversationMessage,
  type ConversationMessage,
  type ConversationScope,
} from '../services/entityConversationApi';
import { LeadRespondMessagesTab } from './LeadRespondMessagesTab';

const FAB_STORAGE_KEY = 'commercial-entity-activities-dock-fab-pos';
const FAB_SIZE_PX = 48;
const FAB_MARGIN_PX = 8;

function pinnedFabX(): number {
  if (typeof window === 'undefined') return 0;
  return Math.max(FAB_MARGIN_PX, window.innerWidth - FAB_SIZE_PX - FAB_MARGIN_PX);
}

export type EntityActivitiesDockProps = EntityActivitiesDockRegistration;

function loadFabPosition(): { x: number; y: number } | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(FAB_STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as { x?: unknown; y?: unknown };
    if (typeof p.x === 'number' && typeof p.y === 'number' && Number.isFinite(p.x) && Number.isFinite(p.y)) {
      return { x: p.x, y: p.y };
    }
  } catch {
    /* ignore */
  }
  return null;
}

function defaultFabPosition(): { x: number; y: number } {
  if (typeof window === 'undefined') return { x: 0, y: 120 };
  return {
    x: pinnedFabX(),
    y: window.innerHeight / 2 - FAB_SIZE_PX / 2,
  };
}

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

type PanelInnerProps = {
  variant: EntityActivitiesDockRegistration['variant'];
  entityId: string;
  canPost: boolean;
  panelTab: 'activities' | 'internal' | 'messages';
  setPanelTab: (v: 'activities' | 'internal' | 'messages') => void;
  users: ActivityUserOption[];
  sortedMessages: ConversationMessage[];
  isFetching: boolean;
  uid?: string | null;
  sendMessage: (bodyHtml: string) => Promise<void>;
  messagesTabActive: boolean;
  leadIdForMessages?: string | null;
};

function ActivitiesDockPanelInner({
  variant,
  entityId,
  canPost,
  panelTab,
  setPanelTab,
  users,
  sortedMessages,
  isFetching,
  uid,
  sendMessage,
  messagesTabActive,
  leadIdForMessages,
}: PanelInnerProps) {
  const attachmentContext =
    variant === 'project'
      ? { entityType: 'commercial_project' as const, entityId }
      : variant === 'lead'
        ? { entityType: 'commercial_lead' as const, entityId }
        : { entityType: 'commercial_master_quotation' as const, entityId };

  const effectiveLeadIdForMessages = variant === 'lead' ? entityId : leadIdForMessages || null;
  const showMessagesTab = !!effectiveLeadIdForMessages;

  return (
    <Tabs
      value={panelTab}
      onValueChange={(v) => setPanelTab(v as 'activities' | 'internal' | 'messages')}
      className="flex min-h-0 flex-1 flex-col"
    >
      <TabsList
        className={cn(
          'mx-4 mt-4 grid h-auto w-auto rounded-lg bg-muted/50 p-1',
          showMessagesTab ? 'grid-cols-3' : 'grid-cols-2',
        )}
      >
        <TabsTrigger value="activities" className="rounded-md px-3" title="Activities">
          <Activity className="mx-auto size-4" aria-hidden />
          <span className="sr-only">Activities</span>
        </TabsTrigger>
        <TabsTrigger value="internal" className="rounded-md px-3" title="Internal notes">
          <StickyNote className="mx-auto size-4" aria-hidden />
          <span className="sr-only">Internal notes</span>
        </TabsTrigger>
        {showMessagesTab ? (
          <TabsTrigger value="messages" className="rounded-md px-3" title="Messages">
            <MessageSquare className="mx-auto size-4" aria-hidden />
            <span className="sr-only">Messages</span>
          </TabsTrigger>
        ) : null}
      </TabsList>

      <TabsContent value="activities" className="mt-0 flex min-h-0 flex-1 flex-col px-0 pb-0 pt-2 data-[state=inactive]:hidden">
        <ScrollArea className="min-h-0 flex-1 px-4">
          <div className="flex flex-col gap-3 pb-4 pr-2 pt-2">
            {isFetching ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : sortedMessages.length === 0 ? (
              <p className="text-muted-foreground py-6 text-center text-sm">No activity yet.</p>
            ) : (
              sortedMessages.map((m) => <MessageBubble key={m.id} msg={m} currentUserId={uid} />)
            )}
          </div>
        </ScrollArea>
        <div className="border-t border-[#e5e7eb] bg-[#fafafa] p-4">
          {canPost ? (
            <ActivityMessageComposer
              users={users}
              onSend={sendMessage}
              placeholder="Share an update… Use @ to mention someone."
              attachmentContext={attachmentContext}
            />
          ) : (
            <p className="text-muted-foreground text-sm">You don&apos;t have permission to post.</p>
          )}
        </div>
      </TabsContent>

      <TabsContent value="internal" className="mt-0 flex min-h-0 flex-1 flex-col px-0 pb-0 pt-2 data-[state=inactive]:hidden">
        <ScrollArea className="min-h-0 flex-1 px-4">
          <div className="flex flex-col gap-3 pb-4 pr-2 pt-2">
            {isFetching ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : sortedMessages.length === 0 ? (
              <p className="text-muted-foreground py-6 text-center text-sm">No internal notes yet.</p>
            ) : (
              sortedMessages.map((m) => <MessageBubble key={m.id} msg={m} currentUserId={uid} />)
            )}
          </div>
        </ScrollArea>
        <div className="border-t border-[#e5e7eb] bg-[#fafafa] p-4">
          {canPost ? (
            <ActivityMessageComposer
              users={users}
              onSend={sendMessage}
              placeholder="Private notes (only you can see these)…"
              attachmentContext={attachmentContext}
            />
          ) : (
            <p className="text-muted-foreground text-sm">You don&apos;t have permission to edit.</p>
          )}
        </div>
      </TabsContent>

      {showMessagesTab ? (
        <TabsContent
          value="messages"
          className="mt-0 flex min-h-0 flex-1 flex-col px-0 pb-0 pt-2 data-[state=inactive]:hidden"
        >
          <LeadRespondMessagesTab
            leadId={effectiveLeadIdForMessages || ''}
            canPost={canPost}
            active={messagesTabActive}
          />
        </TabsContent>
      ) : null}
    </Tabs>
  );
}

function useActivitiesDockData(
  variant: EntityActivitiesDockRegistration['variant'],
  entityId: string,
  scope: ConversationScope,
  fetchEnabled: boolean,
) {
  return useQuery({
    queryKey: ['entity-conversation', variant, entityId, scope],
    queryFn: async () => {
      if (variant === 'project') {
        return listProjectConversationMessages(entityId, { scope });
      }
      if (variant === 'lead') {
        return listLeadConversationMessages(entityId, { scope });
      }
      return listMasterQuotationConversationMessages(entityId, { scope });
    },
    enabled: fetchEnabled && !!entityId,
  });
}

/**
 * Floating mail button + slide-over sheet. No inline/pinned rail (avoids layout/stacking issues with main content and footer).
 */
export function EntityActivitiesDockHost({ className }: { className?: string }) {
  const { data: session } = useSession();
  const uid = session?.user?.id;

  const { registration } = useEntityActivitiesDock();

  const [sheetOpen, setSheetOpen] = useState(false);
  const [panelTab, setPanelTab] = useState<'activities' | 'internal' | 'messages'>('activities');
  const scope: ConversationScope = panelTab === 'internal' ? 'internal_note' : 'activity';

  const variant = registration?.variant ?? 'project';
  const entityId = registration?.entityId ?? '';
  const canPost = registration?.canPost ?? false;

  const fetchEnabled = Boolean(registration && entityId && sheetOpen);

  const { data: users = [] } = useQuery({
    queryKey: ['user-select-entity-activities-dock'],
    queryFn: async () => {
      const r = await apiFetch('/api/user-management/users/select');
      if (!r.ok) return [] as ActivityUserOption[];
      const raw = await r.json();
      const arr = Array.isArray(raw) ? raw : (raw as { data?: unknown })?.data;
      if (!Array.isArray(arr)) return [];
      return arr
        .map((x: unknown) => {
          const o = x as Record<string, unknown>;
          return {
            id: String(o.id ?? ''),
            name: (o.name as string) ?? null,
            email: String(o.email ?? ''),
          };
        })
        .filter((u) => u.id);
    },
    staleTime: 60_000,
  });

  const { data: messages = [], refetch, isFetching } = useActivitiesDockData(
    variant,
    entityId,
    scope,
    fetchEnabled && panelTab !== 'messages',
  );

  const sortedMessages = useMemo(
    () => [...messages].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [messages],
  );

  const sendMessage = async (bodyHtml: string) => {
    if (!registration) return;
    try {
      if (registration.variant === 'project') {
        await postProjectConversationMessage(registration.entityId, { scope, body_html: bodyHtml });
      } else if (registration.variant === 'lead') {
        await postLeadConversationMessage(registration.entityId, { scope, body_html: bodyHtml });
      } else {
        await postMasterQuotationConversationMessage(registration.entityId, { scope, body_html: bodyHtml });
      }
      toast.success(
        panelTab === 'internal'
          ? 'Saved internal note.'
          : panelTab === 'activities'
            ? 'Posted to activities.'
            : 'Saved.',
      );
      await refetch();
    } catch {
      toast.error('Could not save message.');
    }
  };

  const clampFab = useCallback((x: number, y: number) => {
    if (typeof window === 'undefined') return { x, y };
    const pad = FAB_MARGIN_PX;
    const pinnedX = pinnedFabX();
    const maxY = window.innerHeight - FAB_SIZE_PX - pad;
    return {
      x: pinnedX,
      y: Math.min(Math.max(pad, y), maxY),
    };
  }, []);

  const [fabPos, setFabPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [fabHydrated, setFabHydrated] = useState(false);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);
  const draggedRef = useRef(false);

  useLayoutEffect(() => {
    const saved = loadFabPosition();
    const def = defaultFabPosition();
    setFabPos(clampFab(saved?.x ?? def.x, saved?.y ?? def.y));
    setFabHydrated(true);
  }, [clampFab]);

  useEffect(() => {
    const onResize = () => setFabPos((p) => clampFab(p.x, p.y));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [clampFab]);

  useEffect(() => {
    if (!fabHydrated) return;
    try {
      localStorage.setItem(FAB_STORAGE_KEY, JSON.stringify(fabPos));
    } catch {
      /* ignore */
    }
  }, [fabPos, fabHydrated]);

  const onFabPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return;
    draggedRef.current = false;
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      origX: fabPos.x,
      origY: fabPos.y,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onFabPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const d = dragRef.current;
    if (!d || e.pointerId !== d.pointerId) return;
    const dy = e.clientY - d.startY;
    if (Math.abs(dy) > 4) draggedRef.current = true;
    setFabPos(clampFab(d.origX, d.origY + dy));
  };

  const endFabDrag = (e: React.PointerEvent<HTMLButtonElement>) => {
    const d = dragRef.current;
    if (!d || e.pointerId !== d.pointerId) return;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    dragRef.current = null;
    const didDrag = draggedRef.current;
    draggedRef.current = false;
    if (!didDrag) setSheetOpen(true);
  };

  useEffect(() => {
    setPanelTab('activities');
  }, [entityId, variant]);

  const showFab = Boolean(registration);
  useEffect(() => {
    const applyOffset = () => {
      if (typeof document === 'undefined' || typeof window === 'undefined') return;
      const desktop = window.innerWidth >= 640;
      const offset = sheetOpen && registration && desktop ? '440px' : '0px';
      document.documentElement.style.setProperty('--entity-activities-dock-offset', offset);
    };
    applyOffset();
    window.addEventListener('resize', applyOffset);
    return () => {
      window.removeEventListener('resize', applyOffset);
      document.documentElement.style.setProperty('--entity-activities-dock-offset', '0px');
    };
  }, [sheetOpen, registration]);

  const panelBody =
    registration ? (
      <ActivitiesDockPanelInner
        variant={registration.variant}
        entityId={registration.entityId}
        canPost={registration.canPost}
        panelTab={panelTab}
        setPanelTab={setPanelTab}
        users={users}
        sortedMessages={sortedMessages}
        isFetching={isFetching}
        uid={uid}
        sendMessage={sendMessage}
        messagesTabActive={sheetOpen && panelTab === 'messages'}
        leadIdForMessages={registration.leadIdForMessages}
      />
    ) : null;

  const fabEl =
    showFab && typeof document !== 'undefined' ? (
      <div
        className={cn('pointer-events-none fixed z-40', className)}
        style={{ left: fabPos.x, top: fabPos.y }}
      >
        <Button
          type="button"
          size="sm"
          className="pointer-events-auto h-12 w-12 touch-none rounded-l-xl rounded-r-md border border-[#e5e7eb] border-r-0 bg-white shadow-md hover:bg-[#fef2f2] active:cursor-grabbing cursor-grab select-none"
          aria-label="Open activities and notes — drag to move"
          onPointerDown={onFabPointerDown}
          onPointerMove={onFabPointerMove}
          onPointerUp={endFabDrag}
          onPointerCancel={endFabDrag}
        >
          <Activity className="pointer-events-none size-5 text-[#e7000b]" />
        </Button>
      </div>
    ) : null;

  return (
    <>
      {fabEl ? createPortal(fabEl, document.body) : null}

      {registration ? (
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen} modal={false}>
          <SheetContent
            side="right"
            overlay={false}
            className="flex h-full w-full flex-col gap-0 p-0 sm:max-w-[440px]"
            close
          >
            <SheetHeader className="relative border-b border-[#e5e7eb] px-6 py-4 pe-14 text-start">
              <SheetTitle className="text-lg font-semibold text-[#101828]">Activities &amp; notes</SheetTitle>
              <p className="text-muted-foreground text-sm font-normal">
                Activities are visible to everyone with access. Internal notes are private to you.
              </p>
            </SheetHeader>
            {panelBody}
          </SheetContent>
        </Sheet>
      ) : null}
    </>
  );
}

/**
 * Register this document with the global activities dock. Renders nothing; the host shows FAB + sheet.
 */
export function EntityActivitiesDock({
  variant,
  entityId,
  canPost,
  leadIdForMessages,
  className,
}: EntityActivitiesDockProps) {
  const { setRegistration } = useEntityActivitiesDock();

  useEffect(() => {
    setRegistration({
      variant,
      entityId,
      canPost,
      leadIdForMessages: leadIdForMessages ?? null,
      className,
    });
    return () => setRegistration(null);
  }, [variant, entityId, canPost, leadIdForMessages, className, setRegistration]);

  return null;
}
