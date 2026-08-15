'use client';

/**
 * The one people grid, rendered by BOTH the public intake page and the
 * captain's review page (UAC AC-6.3: read and edit present the same structure).
 *
 * `mode` decides what is *added*, never what moves:
 *
 * - `intake`   - the requester's columns only.
 * - `review`   - the same columns plus collision chips, the lane ledger, and
 *                per-row approve / reject.
 * - `readonly` - the same columns, nothing editable. This is what the requester
 *                sees after submitting, and it is the same grid rather than a
 *                second component, so the two can never disagree about what a
 *                row said.
 *
 * Two renderings of one row model: a `DataGrid` from md up, stacked cards below
 * it. A public intake link is opened on a phone from WhatsApp as often as on a
 * desktop, and a 6-column editable grid inside a horizontal scroller is not
 * something anybody fills in on a 375px screen. Both call the same
 * `onPatchPerson`, so there is one source of truth for what an edit means.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { CollisionChips, LaneChip, ProblemChips, ReviewStatusBadge } from './OnboardingChips';
import type {
  OnboardingPerson,
  OnboardingPersonPatch,
  OnboardingTemplateOption,
} from './types';

export type PeopleGridMode = 'intake' | 'review' | 'readonly';

export interface PeopleGridProps {
  mode: PeopleGridMode;
  people: OnboardingPerson[];
  templates: OnboardingTemplateOption[];
  isLoading?: boolean;
  /**
   * Review mode with the pens taken away: the collision and ledger columns
   * still render (they are what a completed batch is FOR), but every input is
   * disabled and the verdict buttons are hidden. Used once the batch has left
   * review - the server refuses those writes anyway; this stops offering them.
   */
  locked?: boolean;
  onPatchPerson?: (personId: string, patch: OnboardingPersonPatch) => void;
  onRemovePerson?: (personId: string) => void;
  onApprovePerson?: (personId: string) => void;
  onRejectPerson?: (personId: string) => void;
  emptyMessage?: string;
}

/** The note field each mode writes. Intake writes the requester's, review the reviewer's. */
function noteField(mode: PeopleGridMode): 'requester_note' | 'reviewer_note' {
  return mode === 'review' ? 'reviewer_note' : 'requester_note';
}

type BufferedInputProps = Omit<
  ComponentProps<typeof Input>,
  'value' | 'onChange' | 'defaultValue'
> & {
  value: string;
  onCommit: (next: string) => void;
};

/**
 * A text cell that keeps the typing local and tells the parent once, on blur
 * (or Enter).
 *
 * The parent owns the row, so a patch per keystroke means the whole grid
 * re-renders mid-word - and on the review screen it also means a PUT per
 * character, with the refetch that follows racing whatever is being typed next.
 * Buffering makes an edit one event: the field the user actually finished.
 *
 * A value that changes from outside (a refetch, a template pre-fill) still has
 * to land, so it is copied into the buffer whenever the field is NOT focused.
 * While it IS focused, the typing wins - nothing may overwrite a half-typed name.
 */
function BufferedInput({
  value,
  onCommit,
  onFocus,
  onBlur,
  onKeyDown,
  ...rest
}: BufferedInputProps) {
  const [draft, setDraft] = useState(value);
  const focusedRef = useRef(false);
  // What the parent last heard from this field, so Enter-then-blur commits once.
  const committedRef = useRef(value);

  useEffect(() => {
    committedRef.current = value;
    if (!focusedRef.current) setDraft(value);
  }, [value]);

  const commit = (next: string) => {
    if (next === committedRef.current) return;
    committedRef.current = next;
    onCommit(next);
  };

  return (
    <Input
      {...rest}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={(e) => {
        focusedRef.current = true;
        onFocus?.(e);
      }}
      onBlur={(e) => {
        focusedRef.current = false;
        commit(e.target.value);
        onBlur?.(e);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          // Enter inside a grid cell means "I am done with this field", not
          // "submit the page".
          e.preventDefault();
          commit(e.currentTarget.value);
        }
        onKeyDown?.(e);
      }}
    />
  );
}

function TemplateSelect({
  value,
  templates,
  disabled,
  onChange,
}: {
  value: string | null;
  templates: OnboardingTemplateOption[];
  disabled?: boolean;
  onChange: (templateId: string | null) => void;
}) {
  const selected = templates.find((t) => t.id === value) ?? null;
  if (disabled) {
    return <span className="text-sm">{selected?.name ?? 'None'}</span>;
  }
  return (
    // A plain <select>: the options are a short, fixed list of labels with no
    // search, and it is the control a phone renders as a native picker.
    <select
      aria-label="Access template"
      className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
    >
      {/* Clearable, because the template is optional (ADR: an optional select
          must be clearable, or a value can be changed but never unset). */}
      <option value="">No template</option>
      {templates.map((template) => (
        <option key={template.id} value={template.id}>
          {template.name}
        </option>
      ))}
    </select>
  );
}

function NeedsCheckboxes({
  person,
  disabled,
  onPatch,
  idPrefix,
}: {
  person: OnboardingPerson;
  disabled: boolean;
  onPatch: (patch: OnboardingPersonPatch) => void;
  idPrefix: string;
}) {
  const items: Array<[keyof OnboardingPersonPatch, string, boolean]> = [
    ['needs_system_account', 'System account', person.needs_system_account],
    ['needs_respond_contact', 'WhatsApp contact', person.needs_respond_contact],
    ['needs_agent_seat', 'Chat-agent seat', person.needs_agent_seat],
  ];
  return (
    <div className="flex flex-col gap-1">
      {items.map(([field, label, checked]) => (
        <label
          key={field}
          htmlFor={`${idPrefix}-${field}`}
          className="flex items-center gap-2 text-xs"
        >
          <Checkbox
            id={`${idPrefix}-${field}`}
            checked={checked}
            disabled={disabled}
            onCheckedChange={(v) => onPatch({ [field]: v === true } as OnboardingPersonPatch)}
          />
          <span>{label}</span>
        </label>
      ))}
    </div>
  );
}

function LaneLedger({ person }: { person: OnboardingPerson }) {
  return (
    <div className="flex flex-col gap-1">
      <LaneChip
        label="System account"
        step={person.user_step}
        error={person.user_error}
        note={person.user_label}
      />
      <LaneChip label="WhatsApp contact" step={person.contact_step} error={person.contact_error} deferred />
      <LaneChip label="Chat-agent seat" step={person.agent_step} error={person.agent_error} deferred />
    </div>
  );
}

export function PeopleGrid({
  mode,
  people,
  templates,
  isLoading = false,
  locked = false,
  onPatchPerson,
  onRemovePerson,
  onApprovePerson,
  onRejectPerson,
  emptyMessage = 'No people yet. Upload a sheet or add a row.',
}: PeopleGridProps) {
  const editable = mode !== 'readonly' && !locked;
  const isReview = mode === 'review';
  const note = noteField(mode);
  const canRemove = Boolean(onRemovePerson);

  // Callers pass these inline (`onPatchPerson={(id, p) => mutate(...)}`), so
  // their identity changes on every parent render. Reading them through a ref
  // keeps the column definitions - and therefore every cell renderer - stable,
  // which is what stops a cell being torn down and remounted while it is being
  // typed into. A shared grid has to be robust to inline handlers rather than
  // asking every caller to memoise.
  const handlersRef = useRef({ onPatchPerson, onRemovePerson, onApprovePerson, onRejectPerson });
  handlersRef.current = { onPatchPerson, onRemovePerson, onApprovePerson, onRejectPerson };

  const patch = useCallback((personId: string, next: OnboardingPersonPatch) => {
    handlersRef.current.onPatchPerson?.(personId, next);
  }, []);

  const columns = useMemo<ColumnDef<OnboardingPerson>[]>(() => {
    const base: ColumnDef<OnboardingPerson>[] = [
      {
        id: 'section',
        accessorFn: (row) => row.section_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Section" column={column} />,
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Section', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.section_label ?? undefined}>
            {row.original.section_label ?? '—'}
          </span>
        ),
      },
      {
        id: 'full_name',
        accessorFn: (row) => row.full_name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 200,
        enableSorting: false,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) =>
          editable ? (
            <BufferedInput
              aria-label={`Name, row ${row.original.row_number}`}
              className="h-8"
              value={row.original.full_name}
              onCommit={(next) => patch(row.original.id, { full_name: next })}
            />
          ) : (
            <span className="truncate block" title={row.original.full_name}>
              {row.original.full_name}
            </span>
          ),
      },
      {
        id: 'nick_name',
        accessorFn: (row) => row.nick_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Nickname" column={column} />,
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Nickname', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) =>
          editable ? (
            <BufferedInput
              aria-label={`Nickname, row ${row.original.row_number}`}
              className="h-8"
              value={row.original.nick_name ?? ''}
              onCommit={(next) => patch(row.original.id, { nick_name: next })}
            />
          ) : (
            <span className="truncate block">{row.original.nick_name ?? '—'}</span>
          ),
      },
      {
        id: 'phone',
        accessorFn: (row) => row.phone_raw ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Phone" column={column} />,
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Phone', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) =>
          editable ? (
            <BufferedInput
              aria-label={`Phone, row ${row.original.row_number}`}
              className="h-8"
              value={row.original.phone_raw ?? ''}
              onCommit={(next) => patch(row.original.id, { phone_raw: next })}
            />
          ) : (
            <span className="truncate block">{row.original.phone_raw ?? '—'}</span>
          ),
      },
      {
        id: 'email',
        accessorFn: (row) => row.email_raw ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Email" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Email', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) =>
          editable ? (
            <BufferedInput
              aria-label={`Email, row ${row.original.row_number}`}
              className="h-8"
              value={row.original.email_raw ?? ''}
              onCommit={(next) => patch(row.original.id, { email_raw: next })}
            />
          ) : (
            <span className="truncate block" title={row.original.email_raw ?? undefined}>
              {row.original.email_raw ?? '—'}
            </span>
          ),
      },
      {
        id: 'template',
        accessorFn: (row) => row.template_id ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Access template" column={column} />,
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Access template', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <TemplateSelect
            value={row.original.template_id}
            templates={templates}
            disabled={!editable}
            onChange={(templateId) => {
              const template = templates.find((t) => t.id === templateId);
              // Picking a template pre-fills the three flags; it does not lock
              // them - the requester confirms, which is the one decision the
              // journey asks of her at this step.
              patch(row.original.id, {
                template_id: templateId,
                ...(template
                  ? {
                      needs_system_account: template.default_needs_system_account,
                      needs_respond_contact: template.default_needs_respond_contact,
                      needs_agent_seat: template.default_needs_agent_seat,
                    }
                  : {}),
              });
            }}
          />
        ),
      },
      {
        id: 'needs',
        accessorFn: (row) => `${row.needs_system_account}`,
        header: ({ column }) => <DataGridColumnHeader title="Needs" column={column} />,
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Needs', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <NeedsCheckboxes
            person={row.original}
            disabled={!editable}
            idPrefix={`grid-${row.original.id}`}
            onPatch={(next) => patch(row.original.id, next)}
          />
        ),
      },
      {
        id: 'problems',
        accessorFn: (row) => row.problems.join(', '),
        header: ({ column }) => <DataGridColumnHeader title="Issues" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Issues', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) =>
          row.original.problems.length ? (
            <ProblemChips problems={row.original.problems} />
          ) : (
            <span className="text-xs text-muted-foreground">None</span>
          ),
      },
      {
        id: 'note',
        accessorFn: (row) => row[noteField(mode)] ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader
            title={mode === 'review' ? 'Reviewer note' : 'Note'}
            column={column}
          />
        ),
        size: 200,
        enableSorting: false,
        meta: {
          headerTitle: mode === 'review' ? 'Reviewer note' : 'Note',
          skeleton: <Skeleton className="h-4 w-28" />,
        },
        cell: ({ row }) =>
          editable ? (
            <BufferedInput
              aria-label={`Note, row ${row.original.row_number}`}
              className="h-8"
              value={row.original[note] ?? ''}
              onCommit={(next) => patch(row.original.id, { [note]: next })}
            />
          ) : (
            <span className="truncate block" title={row.original[note] ?? undefined}>
              {row.original[note] ?? '—'}
            </span>
          ),
      },
    ];

    if (isReview) {
      base.push(
        {
          id: 'collisions',
          accessorFn: (row) => row.collisions.map((c) => c.label).join(', '),
          header: ({ column }) => <DataGridColumnHeader title="Already exists" column={column} />,
          size: 190,
          enableSorting: false,
          meta: { headerTitle: 'Already exists', skeleton: <Skeleton className="h-4 w-28" /> },
          cell: ({ row }) => <CollisionChips collisions={row.original.collisions} />,
        },
        {
          id: 'lanes',
          accessorFn: (row) => row.user_step,
          header: ({ column }) => <DataGridColumnHeader title="Provisioning" column={column} />,
          size: 220,
          enableSorting: false,
          meta: { headerTitle: 'Provisioning', skeleton: <Skeleton className="h-4 w-32" /> },
          cell: ({ row }) => <LaneLedger person={row.original} />,
        },
        {
          id: 'verdict',
          accessorFn: (row) => row.review_status,
          header: ({ column }) => <DataGridColumnHeader title="Verdict" column={column} />,
          size: 180,
          enableSorting: false,
          meta: { headerTitle: 'Verdict', skeleton: <Skeleton className="h-4 w-20" /> },
          cell: ({ row }) => (
            <div className="flex flex-col gap-1">
              <ReviewStatusBadge status={row.original.review_status} />
              {row.original.rejection_reason ? (
                <span
                  className="text-xs text-muted-foreground truncate"
                  title={row.original.rejection_reason}
                >
                  {row.original.rejection_reason}
                </span>
              ) : null}
              {editable ? (
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    onClick={() => handlersRef.current.onApprovePerson?.(row.original.id)}
                  >
                    Keep
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    onClick={() => handlersRef.current.onRejectPerson?.(row.original.id)}
                  >
                    Reject
                  </Button>
                </div>
              ) : null}
            </div>
          ),
        },
      );
    } else if (editable && canRemove) {
      base.push({
        id: 'actions',
        header: '',
        size: 70,
        enableHiding: false,
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="outline"
            className="h-7 px-2 text-xs"
            onClick={() => handlersRef.current.onRemovePerson?.(row.original.id)}
          >
            Remove
          </Button>
        ),
      });
    }

    return base;
    // Deliberately no handler identities in here: they come from the ref above,
    // so the columns only change when the SHAPE of the grid does. Recomputing
    // them per keystroke gave every cell a new renderer identity, which React
    // treats as a different component - the cell remounted and the caret was
    // lost after the first character. `canRemove` is a boolean rather than the
    // handler for the same reason.
  }, [editable, isReview, mode, note, templates, canRemove, patch]);

  const table = useReactTable({
    columns,
    data: people,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <>
      {/* Desktop: the shared grid. Wrapped so wide content scrolls inside its
          own container and the page body never scrolls sideways. */}
      <div className="hidden md:block w-full overflow-x-auto" data-testid="people-grid-desktop">
        <DataGrid
          table={table}
          recordCount={people.length}
          isLoading={isLoading}
          emptyMessage={emptyMessage}
          standardToolbar={false}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
        >
          <DataGridTable />
        </DataGrid>
      </div>

      {/* Mobile: one card per person, same handlers. */}
      <div className="md:hidden flex flex-col gap-3" data-testid="people-grid-mobile">
        {isLoading ? (
          <>
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </>
        ) : people.length === 0 ? (
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          people.map((person) => (
            <div key={person.id} className="rounded-lg border p-3 flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground truncate">
                    {person.section_label ?? 'No section'}
                  </p>
                  {editable ? (
                    <BufferedInput
                      aria-label={`Name, row ${person.row_number}`}
                      className="h-8 mt-1"
                      value={person.full_name}
                      onCommit={(next) => patch(person.id, { full_name: next })}
                    />
                  ) : (
                    <p className="font-medium break-words">{person.full_name}</p>
                  )}
                </div>
                {isReview ? <ReviewStatusBadge status={person.review_status} /> : null}
              </div>

              {editable ? (
                <div className="grid grid-cols-1 gap-2">
                  <BufferedInput
                    aria-label={`Nickname, row ${person.row_number}`}
                    className="h-8"
                    placeholder="Nickname"
                    value={person.nick_name ?? ''}
                    onCommit={(next) => patch(person.id, { nick_name: next })}
                  />
                  <BufferedInput
                    aria-label={`Phone, row ${person.row_number}`}
                    className="h-8"
                    placeholder="Phone"
                    value={person.phone_raw ?? ''}
                    onCommit={(next) => patch(person.id, { phone_raw: next })}
                  />
                  <BufferedInput
                    aria-label={`Email, row ${person.row_number}`}
                    className="h-8"
                    placeholder="Email"
                    value={person.email_raw ?? ''}
                    onCommit={(next) => patch(person.id, { email_raw: next })}
                  />
                </div>
              ) : (
                <dl className="text-sm">
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground w-20 shrink-0">Nickname</dt>
                    <dd className="break-words">{person.nick_name ?? '—'}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground w-20 shrink-0">Phone</dt>
                    <dd className="break-words">{person.phone_raw ?? '—'}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground w-20 shrink-0">Email</dt>
                    <dd className="break-words">{person.email_raw ?? '—'}</dd>
                  </div>
                </dl>
              )}

              <TemplateSelect
                value={person.template_id}
                templates={templates}
                disabled={!editable}
                onChange={(templateId) => {
                  const template = templates.find((t) => t.id === templateId);
                  patch(person.id, {
                    template_id: templateId,
                    ...(template
                      ? {
                          needs_system_account: template.default_needs_system_account,
                          needs_respond_contact: template.default_needs_respond_contact,
                          needs_agent_seat: template.default_needs_agent_seat,
                        }
                      : {}),
                  });
                }}
              />

              <NeedsCheckboxes
                person={person}
                disabled={!editable}
                idPrefix={`card-${person.id}`}
                onPatch={(next) => patch(person.id, next)}
              />

              <ProblemChips problems={person.problems} />
              {isReview ? (
                <>
                  <CollisionChips collisions={person.collisions} />
                  <LaneLedger person={person} />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 px-2 text-xs"
                      onClick={() => handlersRef.current.onApprovePerson?.(person.id)}
                    >
                      Keep
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 px-2 text-xs"
                      onClick={() => handlersRef.current.onRejectPerson?.(person.id)}
                    >
                      Reject
                    </Button>
                  </div>
                </>
              ) : null}
              {editable && onRemovePerson ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 text-xs self-start"
                  onClick={() => onRemovePerson(person.id)}
                >
                  Remove
                </Button>
              ) : null}
            </div>
          ))
        )}
      </div>
    </>
  );
}
