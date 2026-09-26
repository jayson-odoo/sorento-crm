'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { GripVertical } from 'lucide-react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { restrictToParentElement, restrictToVerticalAxis } from '@dnd-kit/modifiers';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  type ColumnDef,
  type SortingState,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { readableValue } from '@/lib/spec-readable';
import { DeferredCountdown } from '@/components/common/DeferredActionButton';
import { compileBuilder, ruleCells } from '../lib/ruleSentence';
import type {
  SpecDerivationRule,
  SpecRegistryKey,
  SpecRuleBuilder,
  SpecRuleProductFact,
  SpecRuleSizePick,
  SpecTryRuleRead,
} from '../types/productSpec.types';

/** A patched builder replaces the rule's `pattern` too (contract section 3: the
 *  stored rule is `{builder, pattern}`, and `pattern` must be whatever
 *  `compileBuilder` says THIS builder compiles to, never a stale one from
 *  before the inline edit). */
function withPattern(builder: SpecRuleBuilder): SpecDerivationRule['pattern'] {
  return compileBuilder(builder).pattern;
}

const SIZE_PICK_OPTIONS: { value: string; label: string }[] = [
  { value: '1', label: '1st number' },
  { value: '2', label: '2nd number' },
  { value: '3', label: '3rd number' },
  { value: '4', label: '4th number' },
  { value: 'L', label: 'Labelled: L' },
  { value: 'W', label: 'Labelled: W' },
  { value: 'H', label: 'Labelled: H' },
];

const PRODUCT_FACT_OPTIONS: { value: SpecRuleProductFact; label: string }[] = [
  { value: 'class', label: "The product's category's class" },
  { value: 'name', label: "What the product's name says it is" },
  { value: 'length', label: "The product's length" },
  { value: 'width', label: "The product's width" },
  { value: 'height', label: "The product's height" },
];

interface GridRow {
  rule: SpecDerivationRule;
  index: number;
  uid: string;
}

/** A rule currently counting down to being removed from the DRAFT list - not yet
 *  saved. Reuses the system's deferred-action countdown UI (D7) purely client-side:
 *  the removal only reaches the server on the record's own Save. */
interface Removal {
  uid: string;
  commitAt: number;
  timer: ReturnType<typeof setTimeout>;
}

const REMOVE_WINDOW_SECONDS = 5;

export interface SpecRulesGridProps {
  rules: SpecDerivationRule[];
  spec: SpecRegistryKey;
  registry: SpecRegistryKey[];
  mode: 'view' | 'edit';
  onChange: (rules: SpecDerivationRule[]) => void;
  onEdit: (index: number) => void;
  onAdd: () => void;
  /** Aligned to `rules` by index (AC-S1.8), from a Try it run at the tab level. */
  reads?: SpecTryRuleRead[] | null;
  winnerIndex?: number | null;
}

/**
 * How a spec is read: a structured grid, one row per rule, one column per part
 * (AC-S1.14). Never a sentence. Sortable headers; What to find and Value it sets
 * edit in place; drag handles only while sorted by Order (AC-S1.9); Remove is a
 * deferred 5s action (AC-S1.10).
 */
export function SpecRulesGrid({
  rules,
  spec,
  registry,
  mode,
  onChange,
  onEdit,
  onAdd,
  reads,
  winnerIndex,
}: SpecRulesGridProps) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'order', desc: false }]);
  const [editingCell, setEditingCell] = useState<{ uid: string; column: 'find' | 'value' } | null>(
    null,
  );
  const [removals, setRemovals] = useState<Record<string, Removal>>({});

  // A pending removal's timer fires up to 5s later, well after the render that
  // scheduled it - refs, not the closed-over props, so an edit made to another
  // rule in the meantime is not clobbered by a commit still holding the old list.
  const rulesRef = useRef(rules);
  rulesRef.current = rules;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Cancel every pending timer on unmount, so leaving the tab mid-countdown does
  // not fire a commit against an unmounted draft.
  useEffect(() => {
    return () => {
      Object.values(removals).forEach((removal) => clearTimeout(removal.timer));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lookupSpec = useMemo(
    () => (specKey: string) => registry.find((k) => k.spec_key === specKey),
    [registry],
  );

  const wordChoices = useMemo(() => {
    const known = new Set<string>();
    for (const rule of rules) {
      if (rule.builder?.kind === 'words') rule.builder.words.forEach((w) => known.add(w));
      if (rule.builder?.kind === 'code') rule.builder.texts.forEach((w) => known.add(w));
    }
    Object.values(spec.synonyms ?? {}).forEach((words) =>
      words.forEach((w) => known.add(w.toUpperCase())),
    );
    return Array.from(known).sort();
  }, [rules, spec.synonyms]);

  const valueOptions = useMemo(
    () =>
      spec.allowed_values.map((value) => ({
        value,
        label: readableValue(value, undefined, spec.value_labels),
      })),
    [spec.allowed_values, spec.value_labels],
  );

  const data = useMemo<GridRow[]>(
    () => rules.map((rule, index) => ({ rule, index, uid: rule._uid ?? `r${index}` })),
    [rules],
  );

  const columns = useMemo<ColumnDef<GridRow>[]>(
    () => [
      { id: 'order', accessorFn: (row) => row.index, enableSorting: true, header: 'Order', size: 70 },
      {
        id: 'where',
        accessorFn: (row) => ruleCells(row.rule.builder, spec, lookupSpec).whereToLook,
        enableSorting: true,
        header: 'Where to look',
        size: 160,
      },
      {
        id: 'kind',
        accessorFn: (row) => ruleCells(row.rule.builder, spec, lookupSpec).kind,
        enableSorting: true,
        header: 'Kind',
        size: 90,
      },
      {
        id: 'find',
        accessorFn: (row) => ruleCells(row.rule.builder, spec, lookupSpec).whatToFind.primary,
        enableSorting: true,
        header: 'What to find',
        size: 300,
      },
      {
        id: 'value',
        accessorFn: (row) => ruleCells(row.rule.builder, spec, lookupSpec).valueItSets,
        enableSorting: true,
        header: 'Value it sets',
        size: 140,
      },
      {
        id: 'only_when',
        accessorFn: (row) => ruleCells(row.rule.builder, spec, lookupSpec).onlyWhen,
        enableSorting: true,
        header: 'Only when',
        size: 160,
      },
      { id: 'actions', header: '', size: 44, enableSorting: false },
    ],
    [spec, lookupSpec],
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.uid,
  });

  const isSortedByOrder = sorting.length === 0 || (sorting[0]?.id === 'order' && !sorting[0]?.desc);
  const sortedRows = table.getSortedRowModel().rows;

  const commitRemoval = (uid: string) => {
    const current = rulesRef.current;
    onChangeRef.current(current.filter((r, i) => (r._uid ?? `r${i}`) !== uid));
    setRemovals((currentRemovals) => {
      const next = { ...currentRemovals };
      delete next[uid];
      return next;
    });
  };

  const startRemoval = (uid: string) => {
    const commitAt = Date.now() + REMOVE_WINDOW_SECONDS * 1000;
    const timer = setTimeout(() => commitRemoval(uid), REMOVE_WINDOW_SECONDS * 1000);
    setRemovals((current) => ({ ...current, [uid]: { uid, commitAt, timer } }));
  };

  const cancelRemoval = (uid: string) => {
    setRemovals((current) => {
      const removal = current[uid];
      if (removal) clearTimeout(removal.timer);
      const next = { ...current };
      delete next[uid];
      return next;
    });
  };

  const moveBy = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= rules.length) return;
    onChange(arrayMove(rules, index, target));
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = rules.findIndex((r, i) => (r._uid ?? `r${i}`) === active.id);
    const to = rules.findIndex((r, i) => (r._uid ?? `r${i}`) === over.id);
    if (from < 0 || to < 0) return;
    onChange(arrayMove(rules, from, to));
  };

  if (rules.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed p-8 text-center">
        <p className="text-sm font-medium">No rules yet</p>
        <p className="text-sm text-muted-foreground">
          Nothing will fill this specification in until a rule is added.
        </p>
        {mode === 'edit' && (
          <Button type="button" size="sm" variant="outline" onClick={onAdd}>
            Add a rule
          </Button>
        )}
      </div>
    );
  }

  const editableFindKinds = new Set(['words', 'code', 'size', 'product']);

  const renderFindCell = (row: GridRow, cells: ReturnType<typeof ruleCells>) => {
    const uid = row.uid;
    const builder = row.rule.builder;
    const editing = editingCell?.uid === uid && editingCell.column === 'find';
    // Every patch recompiles `pattern` from the NEW builder (contract section 3):
    // a stale pattern left over from before the inline edit is what a save's own
    // builder/pattern comparison would refuse.
    const patchBuilder = (next: SpecRuleBuilder) =>
      onChange(
        rules.map((r) => (r._uid === uid ? { ...r, builder: next, pattern: withPattern(next) } : r)),
      );

    if (mode === 'edit' && editing && editableFindKinds.has(builder.kind)) {
      if (builder.kind === 'words') {
        return (
          <SearchableMultiSelect
            value={builder.words}
            onChange={(words) => patchBuilder({ ...builder, words })}
            options={wordChoices.map((w) => ({ value: w, label: w }))}
            createOption={{
              label: (query) => <span>Add &ldquo;{query.toUpperCase()}&rdquo;</span>,
              onCreate: (query) => {
                const upper = query.toUpperCase();
                if (!builder.words.includes(upper)) {
                  patchBuilder({ ...builder, words: [...builder.words, upper] });
                }
              },
            }}
          />
        );
      }
      if (builder.kind === 'code') {
        return (
          <SearchableMultiSelect
            value={builder.texts}
            onChange={(texts) => patchBuilder({ ...builder, texts })}
            options={wordChoices.map((w) => ({ value: w, label: w }))}
            createOption={{
              label: (query) => <span>Add &ldquo;{query.toUpperCase()}&rdquo;</span>,
              onCreate: (query) => {
                const upper = query.toUpperCase();
                if (!builder.texts.includes(upper)) {
                  patchBuilder({ ...builder, texts: [...builder.texts, upper] });
                }
              },
            }}
          />
        );
      }
      if (builder.kind === 'size') {
        return (
          <SearchableSelect
            value={String(builder.pick)}
            onChange={(value) => {
              const pick = (['L', 'W', 'H'].includes(value) ? value : Number(value)) as SpecRuleSizePick;
              patchBuilder({ ...builder, pick });
              setEditingCell(null);
            }}
            options={SIZE_PICK_OPTIONS}
          />
        );
      }
      if (builder.kind === 'product') {
        return (
          <SearchableSelect
            value={builder.fact}
            onChange={(value) => {
              patchBuilder({ ...builder, fact: value as SpecRuleProductFact });
              setEditingCell(null);
            }}
            options={PRODUCT_FACT_OPTIONS}
          />
        );
      }
    }
    const canEditFind = mode === 'edit' && editableFindKinds.has(builder.kind);
    return (
      <button
        type="button"
        disabled={!canEditFind}
        onClick={() => canEditFind && setEditingCell({ uid, column: 'find' })}
        className={`block w-full text-left ${canEditFind ? 'cursor-pointer hover:underline' : ''}`}
      >
        <span className="block truncate font-medium" title={cells.whatToFind.primary}>
          {cells.whatToFind.primary || '-'}
        </span>
        {cells.whatToFind.secondary.map((line) => (
          <span key={line} className="block truncate text-xs text-muted-foreground" title={line}>
            {line}
          </span>
        ))}
      </button>
    );
  };

  const renderValueCell = (row: GridRow, cells: ReturnType<typeof ruleCells>) => {
    const uid = row.uid;
    const builder = row.rule.builder;
    const canEdit =
      mode === 'edit' && (builder.kind === 'words' || builder.kind === 'code') && spec.data_type !== 'boolean';
    const editing = editingCell?.uid === uid && editingCell.column === 'value';
    const patchBuilderValue = (value: string | number | boolean) =>
      onChange(
        rules.map((r) =>
          r._uid === uid && (r.builder.kind === 'words' || r.builder.kind === 'code')
            ? { ...r, builder: { ...r.builder, value }, pattern: withPattern({ ...r.builder, value }) }
            : r,
        ),
      );
    if (editing && canEdit) {
      if (spec.data_type === 'numeric') {
        return (
          <Input
            type="number"
            autoFocus
            defaultValue={String(builder.value ?? '')}
            onBlur={(e) => {
              const value = Number(e.target.value);
              patchBuilderValue(Number.isFinite(value) ? value : builder.value);
              setEditingCell(null);
            }}
          />
        );
      }
      return (
        <SearchableSelect
          value={String(builder.value)}
          onChange={(value) => {
            patchBuilderValue(value);
            setEditingCell(null);
          }}
          options={valueOptions}
        />
      );
    }
    return (
      <button
        type="button"
        disabled={!canEdit}
        onClick={() => canEdit && setEditingCell({ uid, column: 'value' })}
        className={`block w-full truncate text-left ${canEdit ? 'cursor-pointer hover:underline' : ''}`}
        title={cells.valueItSets}
      >
        {cells.valueItSets}
      </button>
    );
  };

  return (
    <DataGrid table={table} recordCount={data.length} tableLayout={{ width: 'fixed', columnsResizable: true }}>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col style={{ width: 70 }} />
            <col style={{ width: 160 }} className="hidden sm:table-column" />
            <col style={{ width: 90 }} className="hidden sm:table-column" />
            <col style={{ width: 300 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 160 }} className="hidden sm:table-column" />
            <col style={{ width: 44 }} />
          </colgroup>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b bg-muted/40">
                {headerGroup.headers.map((header, headerIndex) => (
                  <th
                    key={header.id}
                    className={`p-2 text-left font-medium ${
                      headerIndex === 1 || headerIndex === 2 || headerIndex === 5
                        ? 'hidden sm:table-cell'
                        : ''
                    }`}
                  >
                    {header.column.id === 'actions' ? null : (
                      <DataGridColumnHeader column={header.column} title={String(header.column.columnDef.header)} />
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            modifiers={[restrictToVerticalAxis, restrictToParentElement]}
            onDragEnd={onDragEnd}
          >
            <SortableContext
              items={sortedRows.map((r) => r.original.uid)}
              strategy={verticalListSortingStrategy}
            >
              <tbody>
                {sortedRows.map((row) => {
                  const gridRow = row.original;
                  const removal = removals[gridRow.uid];
                  const cells = ruleCells(gridRow.rule.builder, spec, lookupSpec);
                  const isWinner = winnerIndex === gridRow.index;
                  const readForRow = reads?.[gridRow.index];
                  const canDrag = mode === 'edit' && isSortedByOrder;
                  return (
                    <SpecRuleRow
                      key={gridRow.uid}
                      id={gridRow.uid}
                      canDrag={canDrag}
                      isWinner={isWinner}
                    >
                      {(drag) => (
                        <>
                      <td className="p-2 tabular-nums">
                        <span className="flex items-center gap-1.5">
                          {canDrag && (
                            <button
                              type="button"
                              className="cursor-grab text-muted-foreground active:cursor-grabbing"
                              aria-label={`Drag to reorder rule ${gridRow.index + 1}`}
                              {...drag.attributes}
                              {...drag.listeners}
                            >
                              <GripVertical className="size-3.5" />
                            </button>
                          )}
                          {gridRow.index + 1}
                        </span>
                      </td>
                      <td className="hidden truncate p-2 sm:table-cell" title={cells.whereToLook}>
                        {cells.whereToLook}
                      </td>
                      <td className="hidden truncate p-2 sm:table-cell">{cells.kind}</td>
                      <td className="p-2">
                        {removal ? (
                          <div className="flex flex-col gap-1">
                            <span className="text-xs text-destructive line-through">
                              {cells.whatToFind.primary}
                            </span>
                            <DeferredCountdown
                              pending={{
                                id: gridRow.uid,
                                action_key: 'spec_rule.remove',
                                entity_type: 'spec_rule',
                                entity_id: gridRow.uid,
                                commit_at: new Date(removal.commitAt).toISOString(),
                                window_seconds: REMOVE_WINDOW_SECONDS,
                              }}
                              verb="Removing"
                              onCancel={() => cancelRemoval(gridRow.uid)}
                            />
                          </div>
                        ) : (
                          renderFindCell(gridRow, cells)
                        )}
                        {readForRow !== undefined && !removal && (
                          <div className="mt-1 text-xs text-muted-foreground">
                            Reads:{' '}
                            {readForRow?.value === null || readForRow?.value === undefined
                              ? readForRow?.evidence || 'nothing'
                              : String(readForRow.value)}
                          </div>
                        )}
                      </td>
                      <td className="p-2">{!removal && renderValueCell(gridRow, cells)}</td>
                      <td className="hidden truncate p-2 sm:table-cell" title={cells.onlyWhen}>
                        {cells.onlyWhen || '-'}
                      </td>
                      <td className="p-2">
                        {mode === 'edit' && !removal && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                aria-label={`Rule ${gridRow.index + 1} actions`}
                              >
                                &#8943;
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => onEdit(gridRow.index)}>Edit</DropdownMenuItem>
                              <DropdownMenuItem
                                disabled={!isSortedByOrder}
                                onClick={() => moveBy(gridRow.index, -1)}
                              >
                                Move up
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                disabled={!isSortedByOrder}
                                onClick={() => moveBy(gridRow.index, 1)}
                              >
                                Move down
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() => startRemoval(gridRow.uid)}
                              >
                                Remove
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </td>
                        </>
                      )}
                    </SpecRuleRow>
                  );
                })}
              </tbody>
            </SortableContext>
          </DndContext>
        </table>
      </div>
      <div className="flex items-center justify-between p-2 text-xs text-muted-foreground">
        <span>
          {rules.length} rule{rules.length === 1 ? '' : 's'}. The first rule that finds something wins.
        </span>
        {mode === 'edit' && (
          <Button type="button" size="sm" variant="outline" onClick={onAdd}>
            Add a rule
          </Button>
        )}
      </div>
    </DataGrid>
  );
}

/** One draggable row. `useSortable` needs its own hook call per row, so this is a
 *  component rather than an inline closure in the parent's `.map()`; the drag
 *  handle itself renders wherever `children` puts it (the Order cell), via the
 *  render-prop, so the column count still matches the header. */
function SpecRuleRow({
  id,
  canDrag,
  isWinner,
  children,
}: {
  id: string;
  canDrag: boolean;
  isWinner: boolean;
  children: (drag: {
    attributes: ReturnType<typeof useSortable>['attributes'];
    listeners: ReturnType<typeof useSortable>['listeners'];
  }) => React.ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
    disabled: !canDrag,
  });
  return (
    <tr
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`border-b ${isDragging ? 'z-10 bg-background shadow-lg' : ''} ${
        isWinner ? 'bg-primary/5' : ''
      }`}
    >
      {children({ attributes, listeners })}
    </tr>
  );
}

export default SpecRulesGrid;
