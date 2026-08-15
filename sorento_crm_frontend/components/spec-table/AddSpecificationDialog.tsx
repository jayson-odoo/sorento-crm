'use client';

import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { readable } from '@/lib/spec-readable';
import type { SpecKeyDefinition } from './types';

/**
 * Add a specification this product does not carry yet.
 *
 * **The keys it MAY carry come first** (AC-A.8). The registry has 52 keys and a Water
 * Closet can legitimately hold about a dozen; an alphabetical list of all 52 asks the
 * reader to know which of `bowl_count` and `flush_type` belongs to what they are
 * looking at. Everything else is one more click away rather than gone, because
 * applicability is computed from `applies_when` and a gate can be wrong.
 *
 * **Creating a key is the last resort, and it is gated** (D7, AC-A.9). A key is
 * vocabulary the ranker and the n8n parser both hold; minting one because the picker
 * was scrolled past is how a catalogue ends up with `finish` and `colour` meaning the
 * same thing and answering half the questions each.
 */

/**
 * The three types a key may be created as, matching the API's editable set.
 *
 * `text` is deliberately absent: the API rejects it, because a free-text key is one
 * nothing can ever be searched for. A vocabulary key is created EMPTY and its words
 * arrive afterwards through the add-a-value flow on the row, which is the path
 * Journey A step 3 already describes - so there is no second place to type a value.
 */
export type SpecDataType = 'enum' | 'numeric' | 'boolean';

// "Dropdown", not "a word from a list": named after the control the user will see,
// which is the thing they already have a word for (captain's call, hands-on test).
const DATA_TYPE_OPTIONS = [
  { value: 'enum', label: 'Dropdown' },
  { value: 'numeric', label: 'A number' },
  { value: 'boolean', label: 'Yes or no' },
];

/** What the server said the proposed label already is. */
export interface SimilarKeyMatch {
  spec_key: string;
  label: string;
  /** spec_key | label | synonym - which of the three the proposal collided with. */
  matched_on: string;
  /** The stored text that matched, so the user can see WHY it is the same word. */
  matched_text: string;
}

export function AddSpecificationDialog({
  open,
  onOpenChange,
  applicableKeys,
  otherKeys,
  canCreateKey,
  onPick,
  onCreateKey,
  onCheckSimilar,
  /** Who to ask for the grant. Shown to a user who may not create keys. */
  createDeniedHint = 'Ask an administrator for the Add Spec Registry permission.',
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Keys this product may carry and does not hold. */
  applicableKeys: SpecKeyDefinition[];
  /** Every other key it does not hold, behind the "show everything" switch. */
  otherKeys: SpecKeyDefinition[];
  canCreateKey: boolean;
  onPick: (specKey: string) => void;
  onCreateKey: (input: {
    spec_key: string;
    label: string;
    data_type: SpecDataType;
  }) => Promise<void>;
  /** Null means the label genuinely is new. Runs before the create is offered. */
  onCheckSimilar: (label: string) => Promise<SimilarKeyMatch | null>;
  createDeniedHint?: string;
}) {
  const [showEverything, setShowEverything] = useState(false);
  const [picked, setPicked] = useState('');
  const [creating, setCreating] = useState(false);
  const [proposedLabel, setProposedLabel] = useState('');
  const [proposedType, setProposedType] = useState<SpecDataType>('enum');
  const [match, setMatch] = useState<SimilarKeyMatch | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);

  const options = useMemo(() => {
    const applicable = applicableKeys.map((key) => ({
      value: key.spec_key,
      label: key.label || readable(key.spec_key),
      group: 'Applies to this product',
    }));
    if (!showEverything) return applicable;
    return [
      ...applicable,
      ...otherKeys.map((key) => ({
        value: key.spec_key,
        label: key.label || readable(key.spec_key),
        group: 'Every other specification',
      })),
    ];
  }, [applicableKeys, otherKeys, showEverything]);

  const reset = () => {
    setPicked('');
    setCreating(false);
    setProposedLabel('');
    setProposedType('enum');
    setMatch(null);
    setShowEverything(false);
  };

  const close = () => {
    reset();
    onOpenChange(false);
  };

  /**
   * The duplicate check runs before the create can submit, never after (D7).
   * Offering the match afterwards would mean the key already exists by then.
   */
  const create = async () => {
    const label = proposedLabel.trim();
    if (!label) return;
    setChecking(true);
    try {
      const found = await onCheckSimilar(label);
      setMatch(found);
      if (found) return;
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Could not check for an existing specification',
        { duration: 10_000 },
      );
      return;
    } finally {
      setChecking(false);
    }
    setSaving(true);
    try {
      const specKey = toSpecKey(label);
      await onCreateKey({ spec_key: specKey, label, data_type: proposedType });
      // The key is now vocabulary, and the person who minted it came here to set it on
      // THIS product. Closing without handing it on left them with a key in the registry
      // and a product that never mentions it - the same dead end as picking an existing
      // one used to be.
      onPick(specKey);
      close();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{creating ? 'Create a specification' : 'Add a specification'}</DialogTitle>
          <DialogDescription>
            {creating
              ? 'A new key becomes part of the vocabulary every product shares.'
              : 'Pick the specification to set on this product.'}
          </DialogDescription>
        </DialogHeader>

        {creating ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="spec-new-label">Name</Label>
              <Input
                id="spec-new-label"
                value={proposedLabel}
                onChange={(event) => {
                  setProposedLabel(event.target.value);
                  setMatch(null);
                }}
                placeholder="e.g. Tap hole count"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="spec-new-type">What kind of answer it has</Label>
              <SearchableSelect
                id="spec-new-type"
                value={proposedType}
                onChange={(next) => setProposedType(next as SpecDataType)}
                options={DATA_TYPE_OPTIONS}
              />
            </div>
            {match && (
              <Alert variant="warning" appearance="light">
                <AlertIcon />
                <div className="flex flex-col items-start gap-2">
                  <AlertTitle>
                    {match.matched_on === 'synonym'
                      ? `"${match.matched_text}" is already a word for ${match.label}.`
                      : `${match.label} already exists.`}
                  </AlertTitle>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      onPick(match.spec_key);
                      close();
                    }}
                  >
                    Use {match.label} instead
                  </Button>
                </div>
              </Alert>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <SearchableSelect
              value={picked}
              onChange={setPicked}
              options={options}
              placeholder="Search specifications"
              emptyMessage="No specification matches that."
              clearable
            />
            {!showEverything && otherKeys.length > 0 && (
              <button
                type="button"
                className="w-fit text-sm text-muted-foreground underline underline-offset-2"
                onClick={() => setShowEverything(true)}
              >
                Show every specification ({otherKeys.length} more)
              </button>
            )}
            {canCreateKey ? (
              <button
                type="button"
                className="w-fit text-sm underline underline-offset-2"
                onClick={() => setCreating(true)}
              >
                None of these — create a new specification
              </button>
            ) : (
              // Stated rather than hidden: a person who cannot find their key needs to
              // know a key CAN be created and by whom, or they invent a value instead.
              <p className="text-sm text-muted-foreground">{createDeniedHint}</p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={close} disabled={saving || checking}>
            Cancel
          </Button>
          {creating ? (
            <Button
              onClick={() => void create().catch(() => {})}
              disabled={!proposedLabel.trim() || saving || checking}
            >
              {checking ? 'Checking…' : saving ? 'Creating…' : 'Create'}
            </Button>
          ) : (
            <Button
              onClick={() => {
                onPick(picked);
                close();
              }}
              disabled={!picked}
            >
              Add
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** "Tap hole count" -> `tap_hole_count`, the shape every stored key already has. */
export function toSpecKey(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}
