'use client';

import * as React from 'react';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';

export interface RecordHeaderCardProps {
  /** The record's number, e.g. "OI-2609-0002". */
  title: React.ReactNode;
  /** Status badge(s), inline right after the number. */
  badges?: React.ReactNode;
  /**
   * Muted lines under the title row, each on its own line (owner, 5 Nov 2026: never joined
   * with a middle dot). Empty entries are dropped, so a caller can pass conditionals as is.
   */
  subtitle?: React.ReactNode | React.ReactNode[];
  /** The action group, normally `DetailActions` (pager, gear, primary). */
  actions?: React.ReactNode;
  /** Anything that belongs under the row inside the card (a parked action's countdown). */
  children?: React.ReactNode;
  className?: string;
}

/**
 * The record card at the top of a detail page: number + status inline, one or more muted
 * subtitle lines, and the action group on the right (D6). At narrow widths the actions wrap
 * under the identity.
 *
 * Extracted from Order Inquiry detail (PROPOSAL-HEADER-LAYOUT) so the proposal / quotation page
 * reads the same way and the two cannot drift. Other detail pages still carry an inline copy
 * of this markup; they move over when they are next touched.
 */
export function RecordHeaderCard({
  title,
  badges,
  subtitle,
  actions,
  children,
  className,
}: RecordHeaderCardProps) {
  const lines = (Array.isArray(subtitle) ? subtitle : [subtitle]).filter(
    (line) => line !== null && line !== undefined && line !== false && line !== '',
  );
  return (
    <Card className={className} data-testid="record-header-card">
      <CardHeader className="block py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 flex-col gap-1">
            <div
              className="flex min-w-0 flex-wrap items-center gap-3"
              data-testid="record-header-title-row"
            >
              <CardTitle className="text-lg tabular-nums">{title}</CardTitle>
              {badges}
            </div>
            {lines.map((line, index) => (
              <div
                key={index}
                className="min-w-0 break-words text-sm text-muted-foreground"
                data-testid="record-header-subtitle"
              >
                {line}
              </div>
            ))}
          </div>
          {actions}
        </div>
        {children}
      </CardHeader>
    </Card>
  );
}
