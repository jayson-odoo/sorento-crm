'use client';

import { useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { TraceView } from '../../ai-assistant/components/TraceView';
import { TurnDetailDrawer } from './TurnDetailDrawer';

type OpenTrace = { kind: 'turn'; id: string } | { kind: 'message'; id: string };

/**
 * The one way to open a trace (TRACE-SIDEBAR, owner 11 Nov 2026: "anything that click this
 * trace should open on the sidebar"). Every trace link opens a side drawer over the page it
 * sits on, in the same tab, with the URL untouched; Escape or X closes it. Render
 * `traceDrawer` once and call the opener from the link:
 * - `openTrace(turnId)`: a chatbot turn, in the shared `TurnDetailDrawer`.
 * - `openMessageTrace(messageId)`: an AI assistant reply's span trace (`TraceView`).
 */
export function useTraceDrawer(initialTurnId: string | null = null) {
  const [open, setOpen] = useState<OpenTrace | null>(
    initialTurnId ? { kind: 'turn', id: initialTurnId } : null,
  );
  const close = (next: boolean) => {
    if (!next) setOpen(null);
  };
  // Mounted only while open, so a page with many trace links runs no closed drawer's query.
  const traceDrawer = !open ? null : open.kind === 'turn' ? (
    <TurnDetailDrawer turnId={open.id} onOpenChange={close} />
  ) : (
    <Sheet open onOpenChange={close}>
      <SheetContent
        className="w-full sm:max-w-2xl flex flex-col p-0 overflow-x-hidden"
        aria-describedby={undefined}
      >
        <SheetHeader className="px-4 sm:px-6 py-4 border-b">
          <SheetTitle>Turn trace</SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 sm:px-6 py-4">
          <TraceView messageId={open.id} />
        </div>
      </SheetContent>
    </Sheet>
  );
  return {
    openTrace: (turnId: string | null) =>
      setOpen(turnId ? { kind: 'turn', id: turnId } : null),
    openMessageTrace: (messageId: string) =>
      setOpen({ kind: 'message', id: messageId }),
    traceDrawer,
  };
}
