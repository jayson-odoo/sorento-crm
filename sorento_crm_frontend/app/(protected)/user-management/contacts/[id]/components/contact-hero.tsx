'use client';

import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { getInitials } from '@/lib/helpers';
import type { RespondContact } from '../../types/contact.types';

interface ContactHeroProps {
  contact: RespondContact | undefined;
  isLoading: boolean;
  /** The record's actions: pager, gear, primary (D6). */
  actions?: React.ReactNode;
}

/**
 * The record card: identity on the left, and on the right the pager, the gear
 * and the one primary button (D6) - the same shape as `UserHero`.
 *
 * The phone number is the contact's identity here, the way UserHero echoes a
 * user's name and email, and it stays an editable field inside the Profile tab.
 *
 * The read-only metadata that used to sit beside the actions (Respond.io ID,
 * Created At, Updated At) is in the PAGE HEADER now. Below `lg` the whole
 * right-hand column stacked under the identity, so the pager, the gear, the
 * primary button and a three-column meta grid all landed in a strip at the
 * bottom of the record and read as a footer.
 */
export default function ContactHero({ contact, isLoading, actions }: ContactHeroProps) {
  if (isLoading || !contact) {
    return (
      <div className="flex items-center gap-5 mb-5">
        <Skeleton className="size-14 rounded-full" />
        <div className="space-y-1">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-56" />
        </div>
      </div>
    );
  }

  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-center gap-5 min-w-0">
        <Avatar className="h-14 w-14">
          <AvatarFallback className="text-xl">
            {getInitials(contact.name) || '#'}
          </AvatarFallback>
        </Avatar>
        <div className="space-y-px min-w-0">
          <div className="font-medium text-base font-mono break-words">
            {contact.phone_number}
          </div>
          <div className="text-muted-foreground text-sm break-words">
            {contact.name || 'Unnamed contact'}
          </div>
        </div>
      </div>
      {actions}
    </div>
  );
}
