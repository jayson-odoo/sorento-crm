'use client';

/**
 * The Contacts action set (D15): Impersonate in portal, then Delete.
 *
 * The list row had three icon buttons and the record's gear had Delete alone.
 * One array now, rendered in the row's "..." and in the record's gear. The portal
 * link keeps its own control on both surfaces: it is a two-step send with its own
 * dialog rather than a single menu press.
 *
 * The handlers are passed in because the two surfaces own different dialog state:
 * the list confirms over a row, the record over the record it is showing.
 */

import { Trash2, UserCog } from 'lucide-react';
import type { RecordAction } from '@/components/common/recordActions';
import type { RespondContact } from './types/contact.types';

export interface ContactActionHandlers {
  impersonate: () => void;
  remove: () => void;
}

export function contactActions(
  contact: RespondContact,
  handlers: ContactActionHandlers,
): RecordAction[] {
  return [
    {
      key: 'contact.impersonate',
      label: 'Impersonate in portal',
      icon: UserCog,
      run: handlers.impersonate,
    },
    {
      key: 'contact.delete',
      label: 'Delete contact',
      icon: Trash2,
      kind: 'destructive',
      run: handlers.remove,
    },
  ];
}
