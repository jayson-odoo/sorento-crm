'use client';

import { useState, useRef, useLayoutEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  MoreHorizontal,
  Check,
  Archive,
  RotateCcw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Trash2,
} from 'lucide-react';
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
  /** Permanently delete from database */
  onDelete?: (id: string) => void;
  onInvalidate: () => void;
  selected?: boolean;
  onSelectedChange?: (id: string, checked: boolean) => void;
}

export default function NotificationItem({
  item,
  onMarkRead,
  onMarkUnread,
  onClear,
  onDelete,
  onInvalidate,
  selected = false,
  onSelectedChange,
}: Props) {
  const isUnread = !item.read_at;
  const jobId = item.data?.job_id as string | undefined;
  const isImportJob = item.type?.startsWith('import_job_') && jobId;
  const isPurchaseRequest =
    (item.type === 'purchase_request_created' ||
      item.type === 'purchase_request_updated' ||
      item.type === 'purchase_request_approved') &&
    item.source_entity_type === 'purchase_request' &&
    item.source_entity_id;

  const [expanded, setExpanded] = useState(false);
  const [hasOverflow, setHasOverflow] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el || !item.body) {
      setHasOverflow(false);
      return;
    }
    if (expanded) {
      setHasOverflow(true); // keep "Show less" visible when expanded
      return;
    }
    setHasOverflow(el.scrollHeight > el.clientHeight);
  }, [item.body, expanded]);

  const router = useRouter();
  const handleRowClick = () => {
    if (isUnread) {
      onMarkRead(item.id);
      onInvalidate();
    }
    const link = (item.data as Record<string, unknown> | undefined)?.link;
    if (typeof link === 'string' && link.startsWith('/')) {
      router.push(link);
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

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    void onDelete?.(item.id);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleRowClick}
      onKeyDown={(e) => e.key === 'Enter' && handleRowClick()}
      className={`flex gap-2.5 px-5 py-3 cursor-pointer transition-colors hover:bg-muted/30 ${isUnread ? 'bg-primary/10' : ''} ${selected ? 'bg-muted/50' : ''}`}
    >
      {onSelectedChange ? (
        <div
          className="pt-0.5 shrink-0"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <Checkbox
            checked={selected}
            onCheckedChange={(c) => onSelectedChange(item.id, c === true)}
            aria-label="Select notification"
          />
        </div>
      ) : null}
      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <div className="text-sm font-medium break-words">{item.title}</div>
        {item.body && (
          <div className="text-xs text-muted-foreground break-words">
            <div
              ref={bodyRef}
              className={expanded ? '' : 'line-clamp-2'}
            >
              {item.body}
            </div>
            {hasOverflow && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setExpanded((v) => !v);
                }}
                className="text-xs font-medium text-primary hover:underline mt-1 inline-flex items-center gap-0.5"
              >
                {expanded ? (
                  <>
                    <ChevronUp className="size-3" />
                    Show less
                  </>
                ) : (
                  <>
                    <ChevronDown className="size-3" />
                    Show more
                  </>
                )}
              </button>
            )}
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
        {isPurchaseRequest && (
          <Link
            href={`/procurement-management/purchase-requests/${item.source_entity_id}`}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline mt-2"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="size-3" />
            View form
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
            aria-label="More actions"
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
          {onDelete ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={handleDelete}
              >
                <Trash2 className="size-4 mr-2" />
                Delete
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
