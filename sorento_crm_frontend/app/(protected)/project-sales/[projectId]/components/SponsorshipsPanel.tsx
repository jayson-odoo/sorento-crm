'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink, HandCoins } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
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
  const router = useRouter();
  const sponsorships = useProjectSponsorships(project.id);
  const rollup = useSponsorshipRollup(project.id);

  const rows = React.useMemo(() => sponsorships.data ?? [], [sponsorships.data]);
  type Row = (typeof rows)[number];

  const columns = React.useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: 'request_number',
        accessorFn: (row) => row.request_number ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Form" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium">
            {row.original.request_number ?? '-'}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Form' },
      },
      {
        id: 'status',
        accessorFn: (row) => row.status ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) =>
          row.original.status ? (
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(row.original.status)}`}>
              {row.original.status.replace(/_/g, ' ')}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 150,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'approval_status',
        accessorFn: (row) => row.approval_status ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Approval" column={column} />,
        cell: ({ row }) =>
          row.original.approval_status ? (
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(row.original.approval_status)}`}
            >
              {row.original.approval_status}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 130,
        meta: { headerTitle: 'Approval' },
      },
      {
        id: 'total',
        accessorFn: (row) => Number(row.total_project_value ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        cell: ({ row }) =>
          row.original.total_project_value ? (
            <span className="truncate text-sm font-medium">
              {formatMyr(row.original.total_project_value)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 140,
        meta: { headerTitle: 'Value' },
      },
      {
        id: 'request_date',
        accessorFn: (row) => row.request_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Requested" column={column} />,
        cell: ({ row }) =>
          row.original.request_date ? (
            <span className="truncate text-sm">
              {formatDateInMalaysia(row.original.request_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 130,
        meta: { headerTitle: 'Requested' },
      },
      {
        id: 'subject',
        accessorFn: (row) => row.sponsor_subject ?? '',
        header: ({ column }) => <DataGridColumnHeader title="What for" column={column} />,
        cell: ({ row }) => {
          const subject =
            row.original.sponsor_subject === 'others' && row.original.sponsor_subject_other
              ? row.original.sponsor_subject_other
              : row.original.sponsor_subject?.replace(/_/g, ' ');
          const text = [subject, row.original.purpose].filter(Boolean).join(' - ');
          return text ? (
            <span className="truncate text-sm capitalize" title={text}>
              {text}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          );
        },
        size: 260,
        meta: { headerTitle: 'What for' },
      },
      {
        id: 'customer_name',
        accessorFn: (row) => row.customer_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) =>
          row.original.customer_name ? (
            <span className="truncate text-sm" title={row.original.customer_name}>
              {row.original.customer_name}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 200,
        meta: { headerTitle: 'Customer' },
      },
    ],
    [],
  );

  return (
    <PanelDataGrid
      title="Sponsorships"
      // The rollup is the answer to "what have we already spent chasing this", so it stays
      // in the header. Why there is no Add button is asked once and lives behind the icon.
      toolbar={
        <>
          {rollup.data && rollup.data.form_count > 0 && (
            <Badge variant="secondary" appearance="light" className="gap-1">
              <HandCoins className="size-3" aria-hidden />
              {`${formatMyr(rollup.data.total)} across ${rollup.data.form_count} form${rollup.data.form_count === 1 ? '' : 's'}`}
            </Badge>
          )}
          {(rollup.data?.by_year ?? []).map((year) => (
            <span
              key={year.year}
              className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground"
            >
              <span className="font-medium text-foreground">{year.year}</span>{' '}
              {formatMyr(year.total)}
            </span>
          ))}
          <InfoHint label="About sponsorships">
            Sponsorship spend is recorded on the sponsorship form itself, not here. This
            tab reads the forms that name this project.
          </InfoHint>
        </>
      }
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      listingKey="projects.projects.view::project-sponsorships"
      isLoading={sponsorships.isLoading}
      error={sponsorships.isError ? sponsorships.error : undefined}
      emptyTitle="Nothing sponsored on this project"
      emptyAction={
        <Button asChild variant="outline">
          <Link href="/procurement-management/sponsorship-forms">
            Open sponsorship forms
            <ExternalLink className="size-4" aria-hidden />
          </Link>
        </Button>
      }
      onRowClick={(row) =>
        router.push(`/procurement-management/sponsorship-forms/${row.id}`)
      }
    />
  );
}
