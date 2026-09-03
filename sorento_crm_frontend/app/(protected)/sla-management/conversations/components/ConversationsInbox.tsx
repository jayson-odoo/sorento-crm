'use client';

import { useCallback, useState } from 'react';
import { useSearchParams } from 'next/navigation';

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
 * A contact named in the URL, as a selection.
 *
 * The mention notification deep-links to `?contact=<ref>` and that ref is all it
 * has: the row itself (name, phone, ticket counts) lives in the list, which is
 * paginated and may not have loaded the contact yet. So the thread opens
 * immediately on the ref - which is the only thing every contact-keyed endpoint
 * actually needs - and the real row replaces it as soon as the list produces it.
 * `respond_io_id` stays null until then, which only costs the live stream a few
 * seconds: it subscribes once the row upgrades.
 */
function placeholderSelection(contactRef: string): ConversationInboxItem {
  return {
    contact_ref: contactRef,
    respond_io_id: null,
    phone: null,
    name: null,
    last_message_at: null,
    last_message_snippet: null,
    last_message_direction: null,
    mentioned_at: null,
    open_ticket_count: 0,
    my_open_ticket_count: 0,
    my_open_ticket_id: null,
  };
}

/** A selection that came from the URL and has not met its list row yet. */
function isPlaceholder(item: ConversationInboxItem): boolean {
  return item.respond_io_id === null && item.name === null && item.phone === null;
}

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
  const searchParams = useSearchParams();
  // Only the FIRST value matters: this is a landing instruction, not live state.
  // Re-reading it on every render would fight the user the moment they click a
  // different row (the URL is deliberately left alone).
  const [contactParam] = useState(() => searchParams?.get('contact')?.trim() || null);
  // The mention that produced the deep link is what the Mentioned tab is sorted
  // by (newest note first), so the contact is on its first page - which is what
  // lets the placeholder below upgrade to the real row.
  const [tab, setTab] = useState<ConversationInboxTab>(contactParam ? 'mentioned' : 'mine');
  const [selected, setSelected] = useState<ConversationInboxItem | null>(
    contactParam ? placeholderSelection(contactParam) : null,
  );

  // Only ever replaces the deep-link stub, never a row the user picked: the
  // list re-reads every 30s and swapping the selection on each of those would
  // churn the thread pane's props for nothing.
  const upgradePlaceholder = useCallback((items: ConversationInboxItem[]) => {
    setSelected((current) => {
      if (!current || !isPlaceholder(current)) return current;
      return items.find((item) => item.contact_ref === current.contact_ref) ?? current;
    });
  }, []);

  return (
    // M6-02: dvh - the vh unit sat under mobile Safari's dynamic toolbar, clipping
    // the bottom of the inbox at 375.
    <div className="flex min-h-[70dvh] flex-col gap-4 lg:h-[calc(100dvh-13rem)] lg:flex-row">
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
        onRowsLoaded={upgradePlaceholder}
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
