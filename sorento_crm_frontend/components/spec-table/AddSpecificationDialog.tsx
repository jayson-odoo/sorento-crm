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
 * same thing and answering half the questions each. So "Create" is the LAST entry of
 * the search list, offered for the name just typed and only when no key already goes
 * by it - the same shape as adding a word on a row's value dropdown, which is where
 * the reader learned it. It leads to one question, the type, and then the key is on
 * the product with its editor open.
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
  heldKeys = [],
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
  /** Already on the table. Neither list holds them, so the search must say so itself. */
  heldKeys?: SpecKeyDefinition[];
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
              // The same shape as the value dropdown on a row (captain's call): type
              // the name, and when nothing matches, "Create" is the last entry of the
              // list itself rather than a separate link to hunt for. It leads to the
              // type question, because a key without a type cannot be created.
              // Passed to everyone, because two of the three things it says are about
              // the SEARCH rather than about creating: a name that is already a key, and
              // a name already on this product. Only the Create row itself is gated -
              // `label` returns null for it without the grant, and a null row is not
              // rendered at all.
              createOption={{
                label: (query) => {
                  const known = knownLabel(query, applicableKeys, otherKeys, heldKeys);
                  if (known?.held) {
                    return (
                      <span className="text-muted-foreground">
                        <span className="font-medium text-foreground">{known.key.label}</span>{' '}
                        is already on this product
                      </span>
                    );
                  }
                  if (known) {
                    return (
                      <span className="text-muted-foreground">
                        <span className="font-medium text-foreground">{known.key.label}</span>{' '}
                        already exists — use it
                      </span>
                    );
                  }
                  if (!canCreateKey) return null;
                  return <span>Create &ldquo;{query}&rdquo;</span>;
                },
                onCreate: (query) => {
                  const known = knownLabel(query, applicableKeys, otherKeys, heldKeys);
                  // On the table already: the row is behind this dialog, so there
                  // is nothing to pick and nothing to create.
                  if (known?.held) return;
                  if (known) {
                    // The name IS a key already: pick it, revealing it first if
                    // it was behind the "show everything" fold.
                    if (known.hidden) setShowEverything(true);
                    setPicked(known.key.spec_key);
                    return;
                  }
                  if (!canCreateKey) return;
                  setProposedLabel(query);
                  setMatch(null);
                  setCreating(true);
                },
              }}
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
            {!canCreateKey && (
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

/**
 * The key a typed name already IS, by label or by key, ignoring case and spacing.
 *
 * Only the exact-name case is caught here, so a person who types "Flush type" is
 * pointed at the row instead of offered a duplicate. Near-misses ("Flush kind") are
 * the server's call at Create time (D7), which sees synonyms this list does not.
 *
 * The keys the product already HOLDS are searched too, and neither offerable list
 * contains them: without that, typing the name of a spec sitting on the table read as
 * "no such key, create it", and creating it is the one thing that must not happen.
 */
function knownLabel(
  query: string,
  applicable: SpecKeyDefinition[],
  other: SpecKeyDefinition[],
  held: SpecKeyDefinition[],
): { key: SpecKeyDefinition; hidden: boolean; held: boolean } | null {
  const wanted = toSpecKey(query);
  if (!wanted) return null;
  const same = (key: SpecKeyDefinition) =>
    key.spec_key === wanted || toSpecKey(key.label || '') === wanted;
  const onTable = held.find(same);
  if (onTable) return { key: onTable, hidden: false, held: true };
  const inApplicable = applicable.find(same);
  if (inApplicable) return { key: inApplicable, hidden: false, held: false };
  const inOther = other.find(same);
  if (inOther) return { key: inOther, hidden: true, held: false };
  return null;
}

/** "Tap hole count" -> `tap_hole_count`, the shape every stored key already has. */
export function toSpecKey(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}
