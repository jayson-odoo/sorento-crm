'use client';

import Link from 'next/link';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { MoreHorizontal, Check, Archive, RotateCcw, ExternalLink } from 'lucide-react';
import type { NotificationItem as NotificationItemType } from '@/services/notificationService';

function formatTime(createdAt: string): string {
  // Backend sends naive UTC datetimes without 'Z'; JS parses those as local time.
  // Append 'Z' so we interpret as UTC and get correct relative time.
  const normalized = /[Z+\-]\d{2}:?\d{2}$/.test(createdAt) ? createdAt : `${createdAt}Z`;
  const d = new Date(normalized);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min${diffMins !== 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  return d.toLocaleDateString();
}

interface Props {
  item: NotificationItemType;
  onMarkRead: (id: string) => void;
  onMarkUnread: (id: string) => void;
  onClear: (id: string) => void;
  onInvalidate: () => void;
}

export default function NotificationItem({
  item,
  onMarkRead,
  onMarkUnread,
  onClear,
  onInvalidate,
}: Props) {
  const isUnread = !item.read_at;
  const jobId = item.data?.job_id as string | undefined;
  const isImportJob = item.type?.startsWith('import_job_') && jobId;

  const handleRowClick = () => {
    if (isUnread) {
      onMarkRead(item.id);
      onInvalidate();
    }
  };
  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClear(item.id);
    onInvalidate();
  };
  const handleMarkUnread = (e: React.MouseEvent) => {
    e.stopPropagation();
    onMarkUnread(item.id);
    onInvalidate();
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleRowClick}
      onKeyDown={(e) => e.key === 'Enter' && handleRowClick()}
      className={`flex gap-2.5 px-5 py-3 cursor-pointer transition-colors hover:bg-muted/30 ${isUnread ? 'bg-primary/10' : ''}`}
    >
      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <div className="text-sm font-medium break-words">{item.title}</div>
        {item.body && (
          <div className="text-xs text-muted-foreground line-clamp-2 break-words">
            {item.body}
          </div>
        )}
        <span className="text-xs text-muted-foreground mt-0.5">
          {formatTime(item.created_at)}
        </span>
        {isImportJob && (
          <Link
            href={`/system-management/import-jobs/${jobId}`}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline mt-2"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="size-3" />
            View import job
          </Link>
        )}
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 h-8 w-8"
            onClick={(e) => e.stopPropagation()}
          >
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          {isUnread ? (
            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onMarkRead(item.id); onInvalidate(); }}>
              <Check className="size-4 mr-2" />
              Mark as read
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={handleMarkUnread}>
              <RotateCcw className="size-4 mr-2" />
              Mark as unread
            </DropdownMenuItem>
          )}
          {!item.archived_at && (
            <DropdownMenuItem onClick={handleClear}>
              <Archive className="size-4 mr-2" />
              Clear
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
