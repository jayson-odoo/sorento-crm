'use client';

import Link from 'next/link';
import { Users, ArrowUpRight } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { TeamMemberPreview } from '../types/team.types';

/** Count badge that opens a popover listing the team's members (read-only) with
 * a link to the full Members management page. Replaces the old hand-typed
 * "description" column as the at-a-glance member view. */
export default function TeamMemberPopover({
  teamId,
  teamName,
  members,
  count,
}: {
  teamId: string;
  teamName: string;
  members: TeamMemberPreview[];
  count: number;
}) {
  const initials = (name: string) =>
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join('') || '?';

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1.5 rounded-full border bg-muted/40 px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label={`${count} member${count === 1 ? '' : 's'} in ${teamName}`}
        >
          <Users className="size-3.5" />
          {count}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-64 p-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-semibold">Members</span>
          <span className="text-muted-foreground text-xs">{count}</span>
        </div>
        {count === 0 ? (
          <div className="px-3 py-4 text-center text-sm text-muted-foreground">
            No members yet.
          </div>
        ) : (
          <ScrollArea className="max-h-60">
            <ul className="py-1">
              {members.map((m) => (
                <li
                  key={m.user_id}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm"
                >
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                    {initials(m.name)}
                  </span>
                  <span className="truncate" title={m.name}>
                    {m.name}
                  </span>
                </li>
              ))}
            </ul>
          </ScrollArea>
        )}
        <div className="border-t p-1">
          <Link
            href={`/user-management/teams/${teamId}`}
            className="flex items-center justify-between rounded-sm px-2 py-1.5 text-sm font-medium text-primary hover:bg-muted"
          >
            Manage members
            <ArrowUpRight className="size-4" />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
