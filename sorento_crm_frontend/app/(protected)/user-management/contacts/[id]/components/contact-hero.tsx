'use client';

import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia, getInitials } from '@/lib/helpers';
import type { RespondContact } from '../../types/contact.types';

interface ContactHeroProps {
  contact: RespondContact | undefined;
  isLoading: boolean;
}

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="text-sm font-medium">{children}</div>
    </div>
  );
}

const Empty = () => <span className="text-muted-foreground font-normal">Not set</span>;

/**
 * Identity line plus read-only record metadata.
 *
 * The phone number is the contact's identity here, the way UserHero echoes a user's
 * name and email, and it stays an editable field inside the Profile tab. The meta
 * strip carries ONLY the values with no edit counterpart - Respond.io ID, Created At,
 * Updated At - so the read view and the edit dialog never disagree about a field.
 */
export default function ContactHero({ contact, isLoading }: ContactHeroProps) {
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
    <div className="flex flex-col gap-5 mb-5 lg:flex-row lg:items-center lg:justify-between">
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
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
        <MetaItem label="Respond.io ID">
          {contact.respond_io_id ? (
            <span className="font-mono">{contact.respond_io_id}</span>
          ) : (
            <Empty />
          )}
        </MetaItem>
        <MetaItem label="Created At">{formatDateTimeInMalaysia(contact.created_at)}</MetaItem>
        <MetaItem label="Updated At">{formatDateTimeInMalaysia(contact.updated_at)}</MetaItem>
      </div>
    </div>
  );
}
