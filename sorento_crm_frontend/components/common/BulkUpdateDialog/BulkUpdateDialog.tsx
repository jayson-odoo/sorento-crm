'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, PencilLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
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
import { ScrollArea } from '@/components/ui/scroll-area';
import type { BulkEditableField, BulkUpdateResult } from './types';

/**
 * Reusable, entity-agnostic bulk-edit dialog.
 *
 * SAFE by construction: the caller passes a WHITELIST of `fields` - the user can
 * only pick one of those fields and (for `select`/`user`) only an allowed value.
 * There is no free-form "any column" path. The dialog is a pure UI shell; the
 * actual write is delegated to `onApply(fieldKey, value)`, which the caller wires
 * to a per-resource endpoint that runs each row through the normal update path.
 *
 * Flow: compose (pick field + value) -> AlertDialog confirm -> applying -> result
 * (partial-result summary of updated + skipped rows). Every state is rendered.
 */

export interface BulkUpdateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Number of currently-selected records (drives the summary copy). */
  selectedCount: number;
  /** Whitelist of editable fields. Empty = nothing editable (dialog shows an empty state). */
  fields: BulkEditableField[];
  /** Delegate that performs the update and resolves with a partial result. */
  onApply: (fieldKey: string, value: string) => Promise<BulkUpdateResult>;
}

type Stage = 'compose' | 'result';

export function BulkUpdateDialog({
  open,
  onOpenChange,
  selectedCount,
  fields,
  onApply,
}: BulkUpdateDialogProps) {
  const [stage, setStage] = useState<Stage>('compose');
  const [fieldKey, setFieldKey] = useState<string>('');
  const [value, setValue] = useState<string>('');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState<BulkUpdateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedField = useMemo(
    () => fields.find((f) => f.key === fieldKey) ?? null,
    [fields, fieldKey],
  );

  // Reset everything whenever the dialog is (re)opened so a prior run never leaks.
  useEffect(() => {
    if (open) {
      setStage('compose');
      setFieldKey('');
      setValue('');
      setConfirmOpen(false);
      setApplying(false);
      setResult(null);
      setError(null);
    }
  }, [open]);

  // The human-readable value label for the confirmation summary (never a raw id).
  const valueLabel = useMemo(() => {
    if (!selectedField) return value;
    if (selectedField.type === 'text') return value;
    return selectedField.options?.find((o) => o.value === value)?.label ?? value;
  }, [selectedField, value]);

  const canContinue = Boolean(selectedField) && value.trim().length > 0 && selectedCount > 0;

  const runApply = async () => {
    if (!selectedField) return;
    setApplying(true);
    setError(null);
    try {
      const res = await onApply(selectedField.key, value);
      setResult(res);
      setStage('result');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bulk update failed');
    } finally {
      setApplying(false);
      setConfirmOpen(false);
    }
  };

  const renderValueControl = () => {
    if (!selectedField) return null;
    if (selectedField.type === 'text') {
      return (
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={`New ${selectedField.label.toLowerCase()}`}
        />
      );
    }
    // `select` and `user` both render an allowed-options dropdown. For `user` this
    // is a Phase-1 stub - Phase 2 swaps in `services/userSelectService` (searchable,
    // shows name/email, never the UUID). Options carry the display label so the UI
    // never surfaces a raw id.
    return (
      <SearchableSelect
        value={value}
        onChange={setValue}
        options={(selectedField.options ?? []).map((opt) => ({
          value: opt.value,
          label: opt.label,
        }))}
        placeholder={selectedField.type === 'user' ? 'Select a user…' : 'Select a value…'}
      />
    );
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PencilLine className="size-4" />
              Bulk update
            </DialogTitle>
            <DialogDescription>
              {stage === 'compose'
                ? `Update one field across ${selectedCount} selected record${selectedCount === 1 ? '' : 's'}.`
                : 'Bulk update complete.'}
            </DialogDescription>
          </DialogHeader>

          {stage === 'compose' ? (
            <div className="flex-1 overflow-y-auto space-y-4 px-0.5">
              {fields.length === 0 ? (
                <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                  No fields are enabled for bulk update on this list.
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label>Field to update</Label>
                    <SearchableSelect
                      value={fieldKey}
                      onChange={(v) => {
                        setFieldKey(v);
                        setValue('');
                      }}
                      options={fields.map((f) => ({ value: f.key, label: f.label }))}
                      placeholder="Choose a field…"
                    />
                    <p className="text-xs text-muted-foreground">
                      Only whitelisted fields can be bulk-edited.
                    </p>
                  </div>

                  {selectedField ? (
                    <div className="space-y-1.5">
                      <Label>New value</Label>
                      {renderValueControl()}
                      {selectedField.helpText ? (
                        <p className="text-xs text-muted-foreground">{selectedField.helpText}</p>
                      ) : null}
                    </div>
                  ) : null}

                  {error ? (
                    <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                      <AlertTriangle className="size-4 mt-0.5 shrink-0" />
                      <span>{error}</span>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          ) : (
            <div className="flex-1 overflow-hidden flex flex-col gap-3">
              <div className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm">
                <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
                <span>
                  <span className="font-medium">{result?.updated ?? 0}</span> record
                  {(result?.updated ?? 0) === 1 ? '' : 's'} updated
                  {result && result.skipped.length > 0 ? (
                    <>
                      {' · '}
                      <span className="font-medium">{result.skipped.length}</span> skipped
                    </>
                  ) : null}
                  .
                </span>
              </div>
              {result && result.skipped.length > 0 ? (
                <div className="flex-1 overflow-hidden flex flex-col">
                  <div className="text-sm font-medium mb-1.5 flex items-center gap-1.5">
                    <AlertTriangle className="size-4 text-amber-500" />
                    Skipped rows
                  </div>
                  <ScrollArea className="flex-1 rounded-md border">
                    <ul className="divide-y">
                      {result.skipped.map((s) => (
                        <li key={s.id} className="p-2.5 text-sm">
                          <div className="font-medium">{s.label}</div>
                          <div className="text-xs text-muted-foreground">{s.reason}</div>
                        </li>
                      ))}
                    </ul>
                  </ScrollArea>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  All selected records were updated successfully.
                </p>
              )}
            </div>
          )}

          <DialogFooter>
            {stage === 'compose' ? (
              <>
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  Cancel
                </Button>
                <Button disabled={!canContinue} onClick={() => setConfirmOpen(true)}>
                  Continue
                </Button>
              </>
            ) : (
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Apply-step confirmation - mutating action, so AlertDialog per product standard. */}
      <AlertDialog open={confirmOpen} onOpenChange={(o) => !applying && setConfirmOpen(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Apply bulk update?</AlertDialogTitle>
            <AlertDialogDescription>
              Set <span className="font-medium text-foreground">{selectedField?.label}</span> ={' '}
              <span className="font-medium text-foreground">{valueLabel}</span> on{' '}
              <span className="font-medium text-foreground">{selectedCount}</span> selected record
              {selectedCount === 1 ? '' : 's'}? Each record is validated individually - some may be
              skipped if the change is not allowed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={applying}>Back</AlertDialogCancel>
            <AlertDialogAction
              disabled={applying}
              onClick={(e) => {
                e.preventDefault();
                void runApply();
              }}
            >
              {applying ? (
                <>
                  <Loader2 className="size-4 me-1.5 animate-spin" />
                  Applying…
                </>
              ) : (
                'Apply update'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
