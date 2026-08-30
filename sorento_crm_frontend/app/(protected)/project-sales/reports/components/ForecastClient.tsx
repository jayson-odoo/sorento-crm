'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useProjectDashboard } from '../../_shared/hooks/useProjects';
import type { ForecastBand } from '../../_shared/types/project.types';
import { formatMyr } from '../../[projectId]/components/QuotationsPanel';
import { PageHeader } from '@/components/common/PageHeader';

/**
 * Management reporting (AC-I4), built around the one rule that matters: the three numbers
 * are never blended (AC-I1).
 *
 * That rule is expressed in the LAYOUT, not just in the data. Committed sits on its own,
 * labelled as ordered. Pipeline and Weighted sit together in a visually separate band
 * marked speculative (AC-I2a), so nobody reads a three-year-out guess as revenue. There is
 * no total anywhere on this page, and that is deliberate: a single figure mixing a banked PO
 * with a 10%-probability rumour is exactly the number this module exists to stop producing.
 */
/** Money arrives as a decimal STRING, so `Number` first: "0.00" is falsy as a number and
 *  truthy as a string, which is the wrong answer in the one place it is used. */
function hasMoney(value: string | null | undefined): boolean {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) && amount !== 0;
}

export function ForecastClient() {
  const dashboard = useProjectDashboard();

  if (dashboard.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }

  if (dashboard.isError || !dashboard.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          The dashboard could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {dashboard.error instanceof Error ? dashboard.error.message : 'Try again shortly.'}
        </p>
      </div>
    );
  }

  const { forecast, conversion, loss_reasons, by_salesperson, sponsorship, delivery_lag_months } =
    dashboard.data;
  // `project_count` counts LIVE pursuits only, so on its own it is not a safe test for "is
  // there anything on this page". A company can have money on record and no live project at
  // all: a lost project keeps its purchase order in Committed, because an order does not
  // un-happen. Gating the page on the count alone printed "Nothing to forecast yet" above a
  // real committed figure.
  const hasAnything =
    forecast.project_count > 0 || hasMoney(forecast.committed) || hasMoney(forecast.pipeline);

  return (
    <div className="space-y-5">
      <PageHeader title="Forecast and reports">
        <p className="text-sm text-muted-foreground">
          What is on the table, what it is worth after probability, and what has actually
          been ordered. Three numbers, kept apart.
        </p>
      </PageHeader>

      {!hasAnything ? (
        <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
          <h3 className="text-sm font-semibold">Nothing to forecast yet</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Register a project and the estimate appears as pipeline. Price it and the
            quotation replaces the estimate. Record a PO and it becomes committed.
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="border-primary/40">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Committed
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{formatMyr(forecast.committed)}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Purchase orders on record. The only one of the three that is banked.
                </p>
              </CardContent>
            </Card>

            <Card className="border-dashed lg:col-span-2">
              <CardHeader className="pb-2 flex flex-row items-center justify-between gap-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Speculative
                </CardTitle>
                <Badge variant="secondary" className="text-[11px]">
                  Not revenue
                </Badge>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-2xl font-semibold">{formatMyr(forecast.pipeline)}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Pipeline: open quotations at their current version, or the registration
                    estimate where nothing is priced yet.
                  </p>
                </div>
                <div>
                  <p className="text-2xl font-semibold">{formatMyr(forecast.weighted)}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Weighted by the probability set on each project&apos;s stage. A stage with
                    no probability contributes nothing.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="text-sm">Delivery by year</CardTitle>
              <p className="text-xs text-muted-foreground">
                {`Launch date plus ${delivery_lag_months} months, unless a project states its own window.`}
              </p>
            </CardHeader>
            <CardContent>
              {forecast.by_year.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No project has a launch date or a delivery window yet, so nothing can be
                  placed in a year.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-xs text-muted-foreground">
                        <th className="py-1.5 pe-3 text-start font-medium">Year</th>
                        <th className="py-1.5 pe-3 text-end font-medium">Committed</th>
                        <th className="py-1.5 pe-3 text-end font-medium">
                          Pipeline <span className="font-normal">(speculative)</span>
                        </th>
                        <th className="py-1.5 pe-3 text-end font-medium">
                          Weighted <span className="font-normal">(speculative)</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {forecast.by_year.map((row) => (
                        <tr key={row.year} className="border-b border-border/60">
                          <td className="py-2 pe-3 font-medium">{row.year}</td>
                          <td className="py-2 pe-3 text-end font-medium whitespace-nowrap">
                            {formatMyr(row.committed)}
                          </td>
                          <td className="py-2 pe-3 text-end whitespace-nowrap text-muted-foreground">
                            {formatMyr(row.pipeline)}
                          </td>
                          <td className="py-2 pe-3 text-end whitespace-nowrap text-muted-foreground">
                            {formatMyr(row.weighted)}
                          </td>
                        </tr>
                      ))}
                      {hasUndated(forecast.undated) && (
                        <tr className="border-b border-border/60">
                          <td className="py-2 pe-3 text-muted-foreground">No date yet</td>
                          <td className="py-2 pe-3 text-end whitespace-nowrap">
                            {formatMyr(forecast.undated.committed)}
                          </td>
                          <td className="py-2 pe-3 text-end whitespace-nowrap text-muted-foreground">
                            {formatMyr(forecast.undated.pipeline)}
                          </td>
                          <td className="py-2 pe-3 text-end whitespace-nowrap text-muted-foreground">
                            {formatMyr(forecast.undated.weighted)}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Conversion</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-2xl font-semibold">
                  {conversion.rate ? `${Number(conversion.rate).toFixed(1)}%` : 'Nothing decided yet'}
                </p>
                <p className="text-xs text-muted-foreground">
                  {`${conversion.won} won, ${conversion.lost} lost, ${conversion.open} still open. A project is decided only when its scopes are.`}
                </p>
                {sponsorship.sponsored_projects > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {`Sponsorship: ${formatMyr(sponsorship.sponsored_spend)} across ${sponsorship.sponsored_projects} project${sponsorship.sponsored_projects === 1 ? '' : 's'}, ${sponsorship.converted_projects} of which received a PO.`}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Why we lose</CardTitle>
              </CardHeader>
              <CardContent>
                {loss_reasons.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Nothing has been marked lost yet. Reasons are recorded per scope, so one
                    project can appear under two of them.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {loss_reasons.map((row) => (
                      <li
                        key={row.reason}
                        className="flex items-center justify-between gap-3 text-sm"
                      >
                        <span className="min-w-0 truncate">{row.label}</span>
                        <span className="font-medium">{row.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">By salesperson</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="py-1.5 pe-3 text-start font-medium">Owner</th>
                      <th className="py-1.5 pe-3 text-end font-medium">Projects</th>
                      <th className="py-1.5 pe-3 text-end font-medium">Committed</th>
                      <th className="py-1.5 pe-3 text-end font-medium">Pipeline</th>
                      <th className="py-1.5 pe-3 text-end font-medium">Weighted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {by_salesperson.map((row) => (
                      <tr
                        key={row.owner_user_id ?? 'unassigned'}
                        className="border-b border-border/60"
                      >
                        <td className="py-2 pe-3">
                          {row.owner_name ?? 'Unassigned'}
                        </td>
                        <td className="py-2 pe-3 text-end">{row.project_count}</td>
                        <td className="py-2 pe-3 text-end font-medium whitespace-nowrap">
                          {formatMyr(row.committed)}
                        </td>
                        <td className="py-2 pe-3 text-end whitespace-nowrap text-muted-foreground">
                          {formatMyr(row.pipeline)}
                        </td>
                        <td className="py-2 pe-3 text-end whitespace-nowrap text-muted-foreground">
                          {formatMyr(row.weighted)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function hasUndated(band: ForecastBand): boolean {
  return (
    Number(band.pipeline) !== 0 ||
    Number(band.weighted) !== 0 ||
    Number(band.committed) !== 0
  );
}
