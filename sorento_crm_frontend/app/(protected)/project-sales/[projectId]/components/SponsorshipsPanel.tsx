'use client';

import * as React from 'react';
import Link from 'next/link';
import { ExternalLink, HandCoins } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useProjectSponsorships,
  useSponsorshipRollup,
} from '../../_shared/hooks/useProjects';
import type { Project } from '../../_shared/types/project.types';
import { InfoHint } from './InfoHint';
import { formatMyr } from './QuotationsPanel';

/**
 * Sponsorship spend against this project (AC-F3, AC-F7).
 *
 * Read-only, and that is a decision rather than a shortcut: the sponsorship form is one
 * document owned by procurement (AC-F3, "one form, not two"), so a second editor here
 * would be two places to keep in step. This tab answers "what have we already spent
 * chasing this development" and links out for anything else.
 *
 * The per-year split is shown even for a single year, because the question management
 * asks next is always "and how much of that was this year".
 */
export function SponsorshipsPanel({ project }: { project: Project }) {
  const sponsorships = useProjectSponsorships(project.id);
  const rollup = useSponsorshipRollup(project.id);

  const rows = React.useMemo(() => sponsorships.data ?? [], [sponsorships.data]);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        {/* The one fact worth keeping is why this tab has no Add button, and it is only
            needed once, so it sits behind the icon rather than under the heading. */}
        <div className="flex min-w-0 items-center gap-1">
          <CardTitle className="text-sm">Sponsorships</CardTitle>
          <InfoHint label="About sponsorships">
            Sponsorship spend is recorded on the sponsorship form itself, not here. This
            tab reads the forms that name this project.
          </InfoHint>
        </div>
        {rollup.data && rollup.data.form_count > 0 && (
          <Badge variant="outline" className="gap-1 self-start">
            <HandCoins className="size-3" aria-hidden />
            {`${formatMyr(rollup.data.total)} across ${rollup.data.form_count} form${rollup.data.form_count === 1 ? '' : 's'}`}
          </Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        {rollup.data && rollup.data.by_year.length > 0 && (
          <div className="flex flex-wrap gap-2 text-xs">
            {rollup.data.by_year.map((year) => (
              <span
                key={year.year}
                className="rounded-md border border-border px-2 py-1 text-muted-foreground"
              >
                <span className="font-medium text-foreground">{year.year}</span>{' '}
                {formatMyr(year.total)}
              </span>
            ))}
          </div>
        )}

        {sponsorships.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : sponsorships.isError ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8 text-center">
            <h3 className="text-sm font-semibold text-destructive">
              Sponsorships could not be loaded
            </h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              {sponsorships.error instanceof Error
                ? sponsorships.error.message
                : 'Try again shortly.'}
            </p>
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
            <h3 className="text-sm font-semibold">Nothing sponsored on this project</h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              A sponsorship form links itself to a project when the submitter picks one.
              Older forms carry a typed project title instead and are linked by hand.
            </p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/procurement-management/sponsorship-forms">
                Open sponsorship forms
                <ExternalLink className="size-4" aria-hidden />
              </Link>
            </Button>
          </div>
        ) : (
          <ul className="space-y-2">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2.5 sm:flex-row sm:items-start"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium">
                      {row.request_number ?? 'Unnumbered form'}
                    </span>
                    {row.status && (
                      <Badge variant="outline" className="text-[11px] capitalize">
                        {row.status.replace(/_/g, ' ')}
                      </Badge>
                    )}
                    {row.approval_status && (
                      <Badge
                        variant={row.approval_status === 'rejected' ? 'destructive' : 'secondary'}
                        className="text-[11px] capitalize"
                      >
                        {row.approval_status}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                    {row.total_project_value && (
                      <span className="font-medium text-foreground">
                        {formatMyr(row.total_project_value)}
                      </span>
                    )}
                    {row.request_date && <span>{formatDateInMalaysia(row.request_date)}</span>}
                    {row.customer_name && <span>{row.customer_name}</span>}
                    {row.sponsor_subject && (
                      <span className="capitalize">
                        {row.sponsor_subject === 'others' && row.sponsor_subject_other
                          ? row.sponsor_subject_other
                          : row.sponsor_subject.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                  {row.purpose && (
                    <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
                      {row.purpose}
                    </p>
                  )}
                </div>

                <Button asChild variant="outline" size="sm" className="shrink-0">
                  <Link href={`/procurement-management/sponsorship-forms/${row.id}`}>
                    Open
                    <ExternalLink className="size-3.5" aria-hidden />
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
