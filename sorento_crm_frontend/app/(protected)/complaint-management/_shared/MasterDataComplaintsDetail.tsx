'use client';

/**
 * MasterDataComplaintsDetail - the detail view for one complaint root cause or
 * one complaint resolution: its own fields plus every complaint linked to it.
 *
 * Both domains render through this one component (the only difference is which
 * filter field the linked list uses), so the layout, empty states and links stay
 * identical.
 *
 * Per the CRUD UX standard every section renders even when empty - the linked
 * complaints section shows an explicit empty state with a next-step CTA rather
 * than disappearing.
 */

import Link from 'next/link';
import { MoveLeft } from 'lucide-react';

import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import { LinkedComplaintsPanel } from './LinkedComplaintsPanel';

export interface MasterDataComplaintsDetailProps {
  kind: 'root_cause' | 'resolution';
  id: string;
  /** Fetched record; undefined while loading or when not found. */
  record?: {
    name: string;
    description?: string | null;
    is_active: boolean;
    complaint_count?: number;
  };
  isLoading: boolean;
  /** Where "Back" and the not-found state return to. */
  listHref: string;
  listLabel: string;
}

export function MasterDataComplaintsDetail({
  kind,
  id,
  record,
  isLoading,
  listHref,
  listLabel,
}: MasterDataComplaintsDetailProps) {
  const noun = kind === 'root_cause' ? 'Root cause' : 'Resolution';

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!record) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <p className="text-muted-foreground">{noun} not found</p>
        <Button variant="outline" asChild>
          <Link href={listHref}>
            <MoveLeft className="size-4 mr-1" />
            Back to {listLabel}
          </Link>
        </Button>
      </div>
    );
  }

  const count = record.complaint_count ?? 0;

  return (
    <div className="space-y-6">
      {/* Wraps on mobile: a long name beside actions overflows the page otherwise. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <h1 className="text-xl sm:text-2xl font-semibold leading-tight">
            {noun} - {record.name}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge
              variant={record.is_active ? 'success' : 'secondary'}
              size="sm"
            >
              <BadgeDot />
              {record.is_active ? 'Active' : 'Inactive'}
            </Badge>
            <span>
              {count} linked {count === 1 ? 'complaint' : 'complaints'}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href={listHref}>
              <MoveLeft className="size-4 mr-1" />
              Back to {listLabel}
            </Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm uppercase tracking-wide text-muted-foreground">
            Details
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Name
            </p>
            <p className="mt-1 text-sm font-medium break-words">{record.name}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Description
            </p>
            <p className="mt-1 text-sm break-words">
              {record.description?.trim() ? (
                record.description
              ) : (
                <span className="text-muted-foreground italic">No description</span>
              )}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm uppercase tracking-wide text-muted-foreground">
            Linked complaints
          </CardTitle>
        </CardHeader>
        <CardContent>
          <LinkedComplaintsPanel
            rootCauseId={kind === 'root_cause' ? id : undefined}
            resolutionId={kind === 'resolution' ? id : undefined}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default MasterDataComplaintsDetail;
