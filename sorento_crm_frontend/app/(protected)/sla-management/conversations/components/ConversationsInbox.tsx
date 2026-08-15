'use client';

import { useState } from 'react';

import { useHasPermission } from '@/hooks/usePermissions';
import { cn } from '@/lib/utils';

import ConversationListPane from './ConversationListPane';
import ConversationThreadPane from './ConversationThreadPane';
import type {
  ConversationInboxItem,
  ConversationInboxTab,
} from '../services/conversationsInboxService';

export const CONVERSATIONS_VIEW_PERMISSION = 'sla_management.conversations.view';
export const CONVERSATIONS_REPLY_PERMISSION = 'sla_management.conversations.reply';

/**
 * The Conversations inbox (UAC AC-N1 / AC-N2 / AC-N3): a Respond-like two-pane
 * page - the contact list on the left, the shared thread on the right.
 *
 * Reading a thread here is a PERMISSION, not ticket assignment: a colleague who
 * was reassigned away, one who was mentioned in a note, a manager - all can
 * read. Replying is its own permission on top.
 *
 * At phone width the two panes stack: the list IS the page until a contact is
 * picked, then the thread takes over with a way back. Done with responsive
 * classes rather than a viewport hook so there is no hydration flash.
 */
export default function ConversationsInbox() {
  const canReply = useHasPermission(CONVERSATIONS_REPLY_PERMISSION);
  const [tab, setTab] = useState<ConversationInboxTab>('mine');
  const [selected, setSelected] = useState<ConversationInboxItem | null>(null);

  return (
    <div className="flex min-h-[70vh] flex-col gap-4 lg:h-[calc(100vh-13rem)] lg:flex-row">
      <ConversationListPane
        tab={tab}
        onTabChange={(next) => {
          setTab(next);
          // The picked contact may not be in the new tab at all; keeping it
          // selected would show a thread the list no longer offers.
          setSelected(null);
        }}
        selectedRef={selected?.contact_ref ?? null}
        onSelect={setSelected}
        className={cn(
          'w-full shrink-0 lg:w-80 xl:w-96',
          // Mobile: the thread replaces the list rather than sitting under it.
          selected ? 'hidden lg:flex' : 'flex',
        )}
      />

      <ConversationThreadPane
        contact={selected}
        canReply={canReply}
        onBack={() => setSelected(null)}
        className={cn('min-w-0', selected ? 'flex' : 'hidden lg:flex')}
      />
    </div>
  );
}
