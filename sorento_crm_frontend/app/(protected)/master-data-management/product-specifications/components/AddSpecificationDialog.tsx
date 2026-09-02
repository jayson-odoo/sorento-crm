'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { toSpecKey } from '@/components/spec-table';
import { CREATABLE_SPEC_TYPE_OPTIONS } from '../lib/specTypeLabel';
import { getSimilarSpecKey } from '../services/productSpecService';
import { useSpecRegistryMutations } from '../hooks/useSpecRegistryMutations';
import type { SimilarKeyMatch, SpecDataType } from '@/components/spec-table';

/**
 * Register a specification the registry does not have yet (AC-A.5).
 *
 * Asks for the least it can: a name and a shape. Values, words and rules are all
 * edited on the record page the create navigates to - there is no second form.
 */
export function AddSpecificationDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the new key's slug once the create resolves. */
  onCreated: (specKey: string) => void;
}) {
  const [label, setLabel] = useState('');
  const [dataType, setDataType] = useState<SpecDataType>('enum');
  const [unit, setUnit] = useState('');
  const [checking, setChecking] = useState(false);
  const [match, setMatch] = useState<SimilarKeyMatch | null>(null);
  const { create } = useSpecRegistryMutations();

  const specKey = toSpecKey(label);
  const saving = create.isPending;

  // The near-duplicate warning shows as the label is typed (AC-A.5), 300ms behind the
  // last keystroke, so it is visible well before the reader reaches Add specification.
  useEffect(() => {
    const trimmedLabel = label.trim();
    if (!trimmedLabel) {
      setMatch(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setChecking(true);
      getSimilarSpecKey(trimmedLabel)
        .then((found) => {
          if (!cancelled) setMatch(found);
        })
        .catch(() => {
          // Silent here - submit re-checks and toasts on failure; a keystroke
          // retrying quietly is better than an error on every letter typed.
        })
        .finally(() => {
          if (!cancelled) setChecking(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [label]);

  const reset = () => {
    setLabel('');
    setDataType('enum');
    setUnit('');
    setMatch(null);
  };

  const close = () => {
    reset();
    onOpenChange(false);
  };

  const submit = async () => {
    const trimmedLabel = label.trim();
    if (!trimmedLabel) return;
    // The live check above may still be debouncing (or may have raced a fast typist),
    // so re-check right before writing rather than trusting a possibly-stale `match`.
    if (!match) {
      setChecking(true);
      let found: SimilarKeyMatch | null = null;
      try {
        found = await getSimilarSpecKey(trimmedLabel);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Could not check for an existing specification',
        );
        setChecking(false);
        return;
      }
      setChecking(false);
      if (found) {
        setMatch(found);
        return;
      }
    } else {
      return;
    }
    try {
      await create.mutateAsync({
        spec_key: specKey,
        label: trimmedLabel,
        data_type: dataType,
        unit: dataType === 'numeric' && unit.trim() ? unit.trim() : null,
      });
      toast.success(`${trimmedLabel} added`);
      onCreated(specKey);
      close();
    } catch {
      // useSpecRegistryMutations already toasted the failure.
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a specification</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-spec-label">Label</Label>
            <Input
              id="add-spec-label"
              value={label}
              onChange={(event) => {
                setLabel(event.target.value);
                setMatch(null);
              }}
              placeholder="Rough-in distance"
            />
            {label.trim() && (
              <span className="font-mono text-xs text-muted-foreground">{specKey}</span>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="add-spec-type">Type</Label>
            <SearchableSelect
              id="add-spec-type"
              value={dataType}
              onChange={(next) => setDataType(next as SpecDataType)}
              options={CREATABLE_SPEC_TYPE_OPTIONS}
            />
          </div>
          {dataType === 'numeric' && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="add-spec-unit">Unit</Label>
              <Input
                id="add-spec-unit"
                value={unit}
                onChange={(event) => setUnit(event.target.value)}
                placeholder="mm"
              />
            </div>
          )}
          {match && (
            <Alert variant="warning" appearance="light">
              <AlertIcon />
              <div className="flex flex-col items-start gap-2">
                <AlertTitle>
                  {match.matched_on === 'synonym'
                    ? `"${match.matched_text}" is already a word for ${match.label}.`
                    : `${match.label} already exists.`}
                </AlertTitle>
                <Button size="sm" variant="outline" onClick={close} asChild>
                  <Link
                    href={`/master-data-management/product-specifications/${match.spec_key}`}
                  >
                    Go to {match.label}
                  </Link>
                </Button>
              </div>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={close} disabled={saving || checking}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={!label.trim() || saving || checking}>
            {checking ? 'Checking...' : saving ? 'Adding...' : 'Add specification'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default AddSpecificationDialog;
