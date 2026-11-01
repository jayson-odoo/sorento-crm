'use client';

import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  COARSE_HIT_TARGET_CLASS,
  PRESSED_CLASS,
} from '@/components/ui/primitive-classes';
import { CONTACT_COLUMN_CLASS, REACH_CLASS } from './tickStyles';
import type {
  AccessTypeColumn,
  DocumentAccessRow,
  PreviewContact,
} from '../types/documentAccess.types';
import { RowVerdictPill } from './DocumentAccessVerdict';

interface Props {
  rows: DocumentAccessRow[];
  accessTypes: AccessTypeColumn[];
  contact: PreviewContact | null;
  canEdit: boolean;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  pendingRowId: string | null;
  onOpen: (id: string) => void;
  onTick: (
    row: DocumentAccessRow,
    code: string | null,
    name: string,
    on: boolean,
  ) => void;
}

/** The phone layout of the matrix: one card per type, ticks as wrapping chips that save like the grid ticks. */
export function DocumentAccessCards({
  rows,
  accessTypes,
  contact,
  canEdit,
  isLoading,
  error,
  onRetry,
  pendingRowId,
  onOpen,
  onTick,
}: Props) {
  if (isLoading) {
    return (
      <div role="status" className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    );
  }
  if (error != null && rows.length === 0) {
    return (
      <div className="space-y-2">
        <span role="alert">
          {error instanceof Error && error.message
            ? error.message
            : 'This list could not be loaded.'}
        </span>
        <button
          type="button"
          className="block text-sm underline"
          onClick={onRetry}
        >
          Retry
        </button>
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div>
        <div className="font-medium">No types match</div>
        <div className="text-sm text-muted-foreground">
          Try another name or switch the AI reads filter.
        </div>
      </div>
    );
  }
  const held = new Set(
    contact && contact.runs_as === 'contact' ? contact.access_types : [],
  );
  return (
    <ul className="space-y-3">
      {rows.map((row) => {
        const chips = [
          { code: null as string | null, name: 'Staff', on: row.ai_read_staff },
          ...accessTypes.map((a) => ({
            code: a.code as string | null,
            name: a.name,
            on: row.ai_read_codes.includes(a.code),
          })),
        ];
        return (
          <li
            key={row.id}
            className="cursor-pointer rounded-lg border border-border bg-card p-4"
            onClick={() => onOpen(row.id)}
          >
            <div className="flex items-start justify-between gap-2">
              <button
                type="button"
                className="min-w-0 text-start"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpen(row.id);
                }}
              >
                <div className="break-words font-medium">{row.type_name}</div>
                <div className="text-xs text-muted-foreground">
                  {`${row.readable_count.toLocaleString('en-US')} readable · ${row.file_count.toLocaleString('en-US')} files`}
                </div>
              </button>
              {row.is_direct_access ? (
                <Badge variant="info" appearance="light" className="shrink-0">
                  Direct access
                </Badge>
              ) : null}
            </div>
            <div
              className="mt-3 flex flex-wrap gap-2"
              onClick={(e) => e.stopPropagation()}
            >
              {chips.map((chip) => {
                const reach =
                  chip.code === null
                    ? row.readable_count
                    : (row.reach[chip.code] ?? 0);
                const short =
                  chip.code !== null &&
                  chip.on &&
                  row.readable_count > 0 &&
                  reach < row.readable_count;
                return (
                  <button
                    key={chip.code ?? 'staff'}
                    type="button"
                    role="checkbox"
                    aria-checked={chip.on}
                    aria-label={`${chip.name} reads ${row.type_name}`}
                    disabled={!canEdit || pendingRowId === row.id}
                    onClick={() => onTick(row, chip.code, chip.name, !chip.on)}
                    className={cn(
                      'inline-flex h-8 items-center gap-2 rounded-full border px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60',
                      PRESSED_CLASS,
                      COARSE_HIT_TARGET_CLASS,
                      chip.on
                        ? 'border-primary bg-primary/10'
                        : 'border-border',
                      chip.code &&
                        held.has(chip.code) &&
                        cn('ring-1 ring-primary', CONTACT_COLUMN_CLASS),
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        'size-3 rounded-sm border',
                        chip.on ? 'border-primary bg-primary' : 'border-input',
                      )}
                    />
                    <span>{chip.name}</span>
                    {short ? (
                      <span
                        className={REACH_CLASS}
                        title={`${reach} of ${row.readable_count} documents carry ${chip.name}`}
                      >
                        {`${reach}/${row.readable_count}`}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
            {contact ? (
              <div className="mt-3">
                <RowVerdictPill
                  row={row}
                  contact={contact}
                  accessTypes={accessTypes}
                />
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
