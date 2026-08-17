'use client';

import * as React from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import type {
  ProjectSalesOrderLine,
  SalesOrderRegroupGroup,
} from '../../_shared/types/projectSalesOrder.types';
import { formatMoney, sumMoney } from './SalesOrderMoney';
import { groupExplodedLines } from './SalesOrderLinesTable';

const NEW_GROUP = '__new__';

/**
 * Moves lines between groups and re-splits the draft.
 *
 * Selection is per SET, not per line: a priced parent and its zero-priced companions are one
 * commitment and splitting them across two sales orders would produce a document nobody can
 * fulfil. Everything is local until Re-split, so a half-finished rearrangement writes nothing.
 */
export function SalesOrderRegroupDialog({
  lines,
  currentAreaGroup,
  onDone,
  onConfirm,
  submitting,
}: {
  lines: ProjectSalesOrderLine[];
  currentAreaGroup: string;
  onDone: () => void;
  onConfirm: (groups: SalesOrderRegroupGroup[]) => Promise<unknown>;
  submitting: boolean;
}) {
  const sets = React.useMemo(() => groupExplodedLines(lines), [lines]);

  const [assignment, setAssignment] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(sets.map((set) => [set.key, currentAreaGroup])),
  );
  const [selected, setSelected] = React.useState<Record<string, boolean>>({});
  const [target, setTarget] = React.useState('');
  const [newGroupName, setNewGroupName] = React.useState('');
  const [confirming, setConfirming] = React.useState(false);

  const groupNames = React.useMemo(() => {
    const names = new Set<string>([currentAreaGroup].filter(Boolean));
    Object.values(assignment).forEach((name) => name && names.add(name));
    return [...names];
  }, [assignment, currentAreaGroup]);

  const selectedKeys = Object.keys(selected).filter((key) => selected[key]);

  const groups: SalesOrderRegroupGroup[] = React.useMemo(() => {
    const byName = new Map<string, string[]>();
    sets.forEach((set) => {
      const name = assignment[set.key] || currentAreaGroup;
      const ids = [set.parent.id, ...set.companions.map((companion) => companion.id)];
      byName.set(name, [...(byName.get(name) ?? []), ...ids]);
    });
    return [...byName.entries()].map(([area_group, line_ids]) => ({ area_group, line_ids }));
  }, [assignment, currentAreaGroup, sets]);

  const valueOfGroup = (name: string) =>
    sumMoney(
      sets
        .filter((set) => (assignment[set.key] || currentAreaGroup) === name)
        .flatMap((set) => [set.parent.amount, ...set.companions.map((c) => c.amount)]),
    );

  const move = () => {
    const name = target === NEW_GROUP ? newGroupName.trim() : target;
    if (!name || selectedKeys.length === 0) return;
    setAssignment((current) => {
      const next = { ...current };
      selectedKeys.forEach((key) => {
        next[key] = name;
      });
      return next;
    });
    setSelected({});
    setNewGroupName('');
    setTarget('');
  };

  const unchanged = groups.length === 1 && groups[0].area_group === currentAreaGroup;

  if (confirming) {
    return (
      <AlertDialog open onOpenChange={(next) => !next && setConfirming(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Re-split this sales order?</AlertDialogTitle>
            <AlertDialogDescription>
              {`${groups
                .map((group) => `${group.area_group}: ${group.line_ids.length} lines`)
                .join('. ')}. This shape is remembered for this customer and proposed on their next purchase order.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={submitting}
              onClick={async (event) => {
                event.preventDefault();
                await onConfirm(groups);
                onDone();
              }}
            >
              {submitting ? 'Re-splitting…' : 'Re-split'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-3xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>Move lines between groups</DialogTitle>
          <DialogDescription>
            The shape you publish is remembered for this customer and proposed on their next
            purchase order.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          <div className="flex flex-wrap gap-2">
            {groupNames.map((name) => {
              const count = groups.find((group) => group.area_group === name)?.line_ids.length ?? 0;
              return (
                <span
                  key={name}
                  className="rounded-md border border-border px-2 py-1 text-xs"
                  title={`${name}: ${count} lines, ${formatMoney(valueOfGroup(name))}`}
                >
                  <span className="font-medium">{name}</span>
                  {` · ${count} lines · ${formatMoney(valueOfGroup(name))}`}
                </span>
              );
            })}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="w-full space-y-1.5 sm:w-64">
              <Label htmlFor="regroup-target">Move the selected sets to</Label>
              <SearchableSelect
                id="regroup-target"
                value={target}
                onChange={setTarget}
                options={[
                  ...groupNames.map((name) => ({ value: name, label: name })),
                  { value: NEW_GROUP, label: 'A new group' },
                ]}
                placeholder="Select a group"
                size="sm"
              />
            </div>
            {target === NEW_GROUP && (
              <div className="w-full space-y-1.5 sm:w-56">
                <Label htmlFor="regroup-new-name">New group name</Label>
                <Input
                  id="regroup-new-name"
                  className="h-8"
                  value={newGroupName}
                  onChange={(event) => setNewGroupName(event.target.value)}
                  placeholder="TOWER B"
                />
              </div>
            )}
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={
                selectedKeys.length === 0 ||
                !target ||
                (target === NEW_GROUP && !newGroupName.trim())
              }
              onClick={move}
            >
              {`Move ${selectedKeys.length || ''}`.trim()}
            </Button>
          </div>

          <ul className="space-y-1.5">
            {sets.map((set) => {
              const componentCount = set.companions.length + 1;
              return (
                <li
                  key={set.key}
                  className="flex items-start gap-2 rounded-md border border-border px-3 py-2"
                >
                  <Checkbox
                    id={`regroup-${set.key}`}
                    checked={Boolean(selected[set.key])}
                    onCheckedChange={(next) =>
                      setSelected((current) => ({ ...current, [set.key]: next === true }))
                    }
                    aria-label={`Select line ${set.parent.line_no}`}
                  />
                  <label htmlFor={`regroup-${set.key}`} className="min-w-0 flex-1 cursor-pointer">
                    <span className="flex flex-wrap items-center gap-x-2 text-sm">
                      <span className="font-medium">{`Line ${set.parent.line_no}`}</span>
                      <span className="truncate" title={set.parent.product_code ?? ''}>
                        {set.parent.product_code || 'Not resolved'}
                      </span>
                      {componentCount > 1 && (
                        <span className="text-xs text-muted-foreground">
                          {`${componentCount} components`}
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                      <span>{assignment[set.key] || currentAreaGroup}</span>
                      <span>{set.parent.phase_label || 'Unlabeled phase'}</span>
                      <span>
                        {set.parent.delivery_date
                          ? formatDateInMalaysia(set.parent.delivery_date)
                          : 'No date'}
                      </span>
                      <span>{formatMoney(set.parent.amount)}</span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>

          {sets.length === 0 && (
            <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              This draft has no lines to move.
            </p>
          )}
        </DialogBody>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onDone}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={unchanged || sets.length === 0}
            onClick={() => setConfirming(true)}
          >
            Re-split
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
