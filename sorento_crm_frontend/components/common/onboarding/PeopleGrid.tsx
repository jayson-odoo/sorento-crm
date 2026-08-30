'use client';

/**
 * The one people grid, rendered by BOTH the public intake page and the
 * captain's review page (UAC AC-6.3: read and edit present the same structure).
 *
 * `mode` decides what is *added*, never what moves:
 *
 * - `intake` - the requester's columns only.
 * - `review` - the same columns plus collision chips, the lane ledger, and
 *                per-row approve / reject.
 * - `readonly` - the same columns, nothing editable. This is what the requester
 *                sees after submitting, and it is the same grid rather than a
 *                second component, so the two can never disagree about what a
 *                row said.
 *
 * One rendering, at every width: the embedded-grid idiom (DataGrid > Card >
 * CardTable > DataGridTable) that every other detail-page grid uses, scrolling
 * horizontally inside its own card on a phone. A second, hand-rolled card
 * layout for small screens used to live here; two renderings of one row model
 * is exactly how the two views start disagreeing.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type ReactNode,
} from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { Trash2 } from 'lucide-react';
import { Card, CardHeader, CardHeading, CardTable, CardTitle, CardToolbar } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { CollisionChips, LaneChip, ReviewStatusBadge } from './OnboardingChips';
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
  /** Card heading. The section this grid IS, so it never needs an outer card. */
  title?: string;
  /** Optional line under the heading, e.g. the reviewer's counts strip. */
  description?: ReactNode;
  /** Optional header-right slot, e.g. the intake page's "Add a person". */
  actions?: ReactNode;
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
  personId,
  value,
  templates,
  disabled,
  onChange,
}: {
  personId: string;
  value: string | null;
  templates: OnboardingTemplateOption[];
  disabled?: boolean;
  onChange: (templateId: string | null) => void;
}) {
  const selected = templates.find((t) => t.id === value) ?? null;
  if (disabled) {
    return <span className="text-sm">{selected?.name ?? 'None'}</span>;
  }
  const id = `people-grid-template-${personId}`;
  return (
    <>
      {/* The grid header is a column title, not a per-cell label, so the control
          carries its own for anyone reading the row on its own. */}
      <label htmlFor={id} className="sr-only">
        Access template
      </label>
      <SearchableSelect
        id={id}
        size="sm"
        // The template is optional, so it must be possible to unset it and not
        // only to change it (ADR: an optional select must be clearable).
        clearable
        // A template label is longer than this cell, and a menu cut to the cell
        // width can make two templates read the same.
        wrapOptions
        value={value ?? ''}
        onChange={(next) => onChange(next || null)}
        options={templates.map((template) => ({
          value: template.id,
          label: template.name,
          description: template.description ?? undefined,
        }))}
        placeholder="No template"
      />
    </>
  );
}

/**
 * The three things a person can be given, in the words the captain uses.
 *
 * Labels only: the columns behind them keep their original names
 * (`needs_respond_contact`, `needs_agent_seat`), because renaming a column is a
 * migration and this was a vocabulary decision.
 */
const NEED_FIELDS = [
  'needs_system_account',
  'needs_respond_contact',
  'needs_agent_seat',
] as const;

type NeedField = (typeof NEED_FIELDS)[number];

export const NEED_LABELS: Record<NeedField, string> = {
  needs_system_account: 'System account',
  needs_respond_contact: 'Access to chatbot AI',
  needs_agent_seat: 'Respond.io account',
};

function selectedNeeds(person: OnboardingPerson): NeedField[] {
  return NEED_FIELDS.filter((field) => person[field]);
}

/**
 * What this person needs, as the standard multi-select every other picker in
 * the app uses rather than a stack of checkboxes.
 *
 * Read-only modes render the same words as plain text, so the row says the same
 * thing whether or not it can be edited.
 *
 * The trigger deliberately does NOT use the component's default removable
 * chips. In a 240px fixed-height cell those chips fill the control, and each one
 * carries an X that unsets that need on pointer-down without opening the menu -
 * measured at 14px from the field's own centre, i.e. under the click that opens
 * it. A stray hit silently dropped a need and the next pick then looked like it
 * had REPLACED the selection, which is exactly how a working multi-select gets
 * reported as a single-select. Here the menu is the only way to change the
 * answer, and the trigger only reports it.
 */
function NeedsSelect({
  personId,
  person,
  disabled,
  onPatch,
}: {
  personId: string;
  person: OnboardingPerson;
  disabled: boolean;
  onPatch: (patch: OnboardingPersonPatch) => void;
}) {
  const chosen = selectedNeeds(person);
  const spoken = chosen.map((field) => NEED_LABELS[field]).join(', ');
  if (disabled) {
    return <span className="text-sm break-words">{spoken || 'Nothing'}</span>;
  }
  const id = `people-grid-needs-${personId}`;
  return (
    <>
      {/* The grid header is a column title, not a per-cell label. */}
      <label htmlFor={id} className="sr-only">
        Needs
      </label>
      <SearchableMultiSelect
        id={id}
        size="sm"
        wrapOptions
        triggerClassName="w-full"
        value={chosen}
        onChange={(next) => {
          // Every flag is sent, not only the one that moved: the selection IS
          // the answer, so an unticked option has to arrive as `false` rather
          // than as an absent key the server would leave alone.
          const set = new Set(next);
          onPatch(
            Object.fromEntries(
              NEED_FIELDS.map((field) => [field, set.has(field)]),
            ) as OnboardingPersonPatch,
          );
        }}
        options={NEED_FIELDS.map((field) => ({ value: field, label: NEED_LABELS[field] }))}
        placeholder="Nothing"
        // Words, not removable chips - see the note above this component. The
        // menu still shows a tick per chosen option, so nothing is hidden.
        renderTriggerLabel={() => (
          <span className="truncate" title={spoken || undefined}>
            {spoken || 'Nothing'}
          </span>
        )}
      />
    </>
  );
}

function LaneLedger({ person }: { person: OnboardingPerson }) {
  return (
    <div className="flex flex-col gap-1">
      <LaneChip
        label={NEED_LABELS.needs_system_account}
        step={person.user_step}
        error={person.user_error}
        note={person.user_label}
      />
      <LaneChip
        label={NEED_LABELS.needs_respond_contact}
        step={person.contact_step}
        error={person.contact_error}
        deferred
      />
      <LaneChip
        label={NEED_LABELS.needs_agent_seat}
        step={person.agent_step}
        error={person.agent_error}
        deferred
      />
    </div>
  );
}

export function PeopleGrid({
  mode,
  people,
  templates,
  isLoading = false,
  title = 'People',
  description,
  actions,
  locked = false,
  onPatchPerson,
  onRemovePerson,
  onApprovePerson,
  onRejectPerson,
  emptyMessage = 'No people yet. Add a person.',
}: PeopleGridProps) {
  const editable = mode !== 'readonly' && !locked;
  const isReview = mode === 'review';
  const note = noteField(mode);
  const canRemove = Boolean(onRemovePerson);
  const [removing, setRemoving] = useState<OnboardingPerson | null>(null);

  // Callers pass these inline (`onPatchPerson={(id, p) => mutate(...)}`), so
  // their identity changes on every parent render. Reading them through a ref
  // keeps the column definitions - and therefore every cell renderer - stable,
  // which is what stops a cell being torn down and remounted while it is being
  // typed into. A shared grid has to be robust to inline handlers rather than
  // asking every caller to memoise.
  const handlersRef = useRef({ onPatchPerson, onRemovePerson, onApprovePerson, onRejectPerson });
  handlersRef.current = { onPatchPerson, onRemovePerson, onApprovePerson, onRejectPerson };

  // `templates` is read through a ref for the same reason, and it is the more
  // dangerous of the two: it arrives on a query response, so a refetch hands
  // over a NEW array holding the same options. As a memo dependency that alone
  // rebuilt every column, and a rebuilt column is a new cell renderer, which
  // React unmounts and remounts - taking the half-typed name in that cell with
  // it. The options themselves change only when an admin edits a template, so
  // the memo is keyed on their identities rather than the array's.
  const templatesRef = useRef(templates);
  templatesRef.current = templates;
  const templateKey = templates.map((t) => t.id).join('|');

  const patch = useCallback((personId: string, next: OnboardingPersonPatch) => {
    handlersRef.current.onPatchPerson?.(personId, next);
  }, []);

  const columns = useMemo<ColumnDef<OnboardingPerson>[]>(() => {
    const base: ColumnDef<OnboardingPerson>[] = [
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
            <span className="truncate block" title={row.original.nick_name ?? undefined}>
              {row.original.nick_name ?? '-'}
            </span>
          ),
      },
      {
        // Free text, not a picker: the requester knows what somebody does, and
        // the reviewer is the one who turns that into a CRM role. Asking her to
        // choose from a role list would leak the very list AC-5.4 hides.
        id: 'role_label',
        accessorFn: (row) => row.role_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Role" column={column} />,
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Role', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          editable ? (
            <BufferedInput
              aria-label={`Role, row ${row.original.row_number}`}
              className="h-8"
              maxLength={120}
              value={row.original.role_label ?? ''}
              onCommit={(next) => patch(row.original.id, { role_label: next })}
            />
          ) : (
            <span className="truncate block" title={row.original.role_label ?? undefined}>
              {row.original.role_label ?? '-'}
            </span>
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
            <span className="truncate block" title={row.original.phone_raw ?? undefined}>
              {row.original.phone_raw ?? '-'}
            </span>
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
              {row.original.email_raw ?? '-'}
            </span>
          ),
      },
      {
        id: 'template',
        accessorFn: (row) => row.template_id ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Access template" column={column} />,
        size: 190,
        enableSorting: false,
        meta: { headerTitle: 'Access template', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <TemplateSelect
            personId={row.original.id}
            value={row.original.template_id}
            templates={templatesRef.current}
            disabled={!editable}
            onChange={(templateId) => {
              const template = templatesRef.current.find((t) => t.id === templateId);
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
        size: 240,
        enableSorting: false,
        meta: { headerTitle: 'Needs', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <NeedsSelect
            personId={row.original.id}
            person={row.original}
            disabled={!editable}
            onPatch={(next) => patch(row.original.id, next)}
          />
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
              {row.original[note] ?? '-'}
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
                  {/* "Approve", the same word the badge and the request-level
                      action use. The endpoint is still `keep`; the reviewer
                      should not have to learn two words for one verdict. */}
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    onClick={() => handlersRef.current.onApprovePerson?.(row.original.id)}
                  >
                    Approve
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
        size: 60,
        enableHiding: false,
        enableSorting: false,
        cell: ({ row }) => (
          // The standard row-delete affordance: a ghost trash icon, the same one
          // every other listing uses, rather than a word only this grid used.
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Remove"
            title="Remove"
            onClick={() => setRemoving(row.original)}
          >
            <Trash2 className="size-4 text-destructive" />
          </Button>
        ),
      });
    }

    return base;
    // Deliberately no handler or template-array identities in here: they come
    // from the refs above, so the columns only change when the SHAPE of the
    // grid does. Recomputing them per keystroke gave every cell a new renderer
    // identity, which React treats as a different component - the cell
    // remounted and the caret was lost after the first character. `canRemove`
    // is a boolean and `templateKey` a string of ids for the same reason.
    //
    // The rule cannot see that `templateKey` stands in for `templatesRef`, so
    // it reads as unnecessary. Removing it is the bug: the picker would then
    // keep rendering options that no longer exist.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable, isReview, mode, note, templateKey, canRemove, patch]);

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
      <DataGrid
        table={table}
        recordCount={people.length}
        isLoading={isLoading}
        emptyMessage={emptyMessage}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        // An embedded grid, not a listing: it has no route of its own, and the
        // default key would persist column preferences per request id and per
        // intake token.
        listingKey=""
      >
        <Card data-testid="people-grid">
          <CardHeader>
            <CardHeading>
              <CardTitle>{title}</CardTitle>
              {description ? (
                <div className="text-sm text-muted-foreground">{description}</div>
              ) : null}
            </CardHeading>
            {actions ? <CardToolbar>{actions}</CardToolbar> : null}
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
        </Card>
      </DataGrid>

      {/* KEPT as a dialog, deliberately, where S6b turned the rest into grace
          windows (D7). The only surface that offers removal is the TOKEN-SCOPED
          intake screen under `app/(auth)/onboarding`, where there is no
          authenticated principal, so `POST /pending-actions` has nobody to check
          a permission slug against and no requester to attribute the action to.
          Removing a row also throws away what she typed, so it stays confirmed
          rather than becoming one click. Mounted only where removal is offered:
          the dialog is query-client backed, and a read-only grid has no business
          requiring one. */}
      {canRemove ? (
        <ConfirmDeleteDialog
          open={!!removing}
          onOpenChange={(open) => !open && setRemoving(null)}
          description={`Remove ${removing?.full_name?.trim() || 'this person'} from this request? This action cannot be undone.`}
          successMessage="Person removed"
          onDelete={async () => {
            if (removing) handlersRef.current.onRemovePerson?.(removing.id);
          }}
        />
      ) : null}
    </>
  );
}
