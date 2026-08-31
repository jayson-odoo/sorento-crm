'use client';

import { useState } from 'react';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { updateSpecKey } from '../services/productSpecService';
import SpecRuleEditor from './SpecRuleEditor';
import TokenInput from './TokenInput';
import { readable } from '@/lib/spec-readable';
import { ruleSentence } from '../lib/ruleSentence';
import { seedValuesFor, seedWordsFor, valuePayload, wordPayload } from '../lib/vocabularyEdit';
import type { SpecDerivationRule, SpecRegistryKey } from '../types/productSpec.types';

/**
 * Edit one spec key.
 *
 * Everything the vocabulary can be is editable here, including the parts that ship with
 * the product. Shipped values and words are not deleted when you remove them - they are
 * suppressed, which is the difference between "this business does not use that" and
 * "that never existed". Suppressed entries stay on screen, struck through, with a way
 * back, so the vocabulary you can see is the whole vocabulary.
 */

/** One labelled control. The label is the only chrome a field needs. */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}

const dedupe = (list: string[]) => Array.from(new Set(list));

/** What a matching product class scores. The strongest signal the ranker has, and so
 *  the ceiling a standing preference has to stay under to remain a preference. */
const CLASS_MATCH_WORTH = 5;

export default function SpecKeyEditor({
  specKey,
  onSaved,
  onCancel,
}: {
  specKey: SpecRegistryKey;
  onSaved: (updated: SpecRegistryKey) => void;
  onCancel: () => void;
}) {


  // What the SEED ships, reconstructed: the live list minus what staff added, plus the
  // shipped values currently taken away. Every "is this mine or theirs" decision below
  // reads this rather than `allowed_values`, which is the merged view and would count a
  // staff-added value as shipped the moment it was saved.
  const seedValues = seedValuesFor(specKey);
  const isOpenVocabulary = specKey.data_type === 'enum' && seedValues.length === 0;
  const isBoolean = specKey.data_type === 'boolean';

  const [label, setLabel] = useState(specKey.label);
  const [weight, setWeight] = useState(String(specKey.rank_weight ?? 1));
  const [tolerance, setTolerance] = useState(String(specKey.match_tolerance ?? 0));
  const [decay, setDecay] = useState(String(specKey.match_decay ?? 0));
  const [active, setActive] = useState(specKey.is_active);
  const [excluded, setExcluded] = useState<string[]>(specKey.excluded_values ?? []);
  // Seeded from the rules that ACTUALLY run, not from the stored column. A key that has
  // never been edited runs the shipped set, and showing the empty column instead told
  // people nothing would ever fill in a key that was already filled in on 74 products.
  // Saving writes them down, which is how an inherited default becomes yours.
  // Given an identity on the way in so dragging moves a RULE, not a position.
  const [rules, setRules] = useState<SpecDerivationRule[]>(() =>
    (specKey.effective_rules ?? specKey.derivation_rules ?? []).map((rule, index) => ({
      ...rule,
      _uid: `r${index}`,
    })),
  );
  // {other_key: [permitted values]}. Only the class gate is edited here, because it is
  // the only one anybody has needed and a generic key/value grid for the rest would be
  // a lot of screen for a case that has not come up.
  const [classScope, setClassScope] = useState<string[]>(specKey.applies_when?.class ?? []);
  const [preferences, setPreferences] = useState(
    Object.entries(specKey.value_weights ?? {})
      .map(([value, bonus]) => `${value} = ${bonus}`)
      .join('\n'),
  );

  // The values in use, and the shipped ones taken away, as two lists rather than one
  // list plus a set of locks: removing a value has to be able to mean different things
  // depending on who owns it, and a lock cannot express that.
  const [liveValues, setLiveValues] = useState<string[]>(specKey.allowed_values);
  const [droppedValues, setDroppedValues] = useState<string[]>(
    specKey.suppressed_values ?? [],
  );

  // Every value that could carry customer wording. A numeric key like bowl_count has no
  // `allowed_values` at all, yet ships words for 1, 2 and 3 - reading the rows off the
  // value list alone rendered an empty section for exactly the keys whose wording
  // matters most. Open vocabularies (brand, class) are the same story.
  //
  // `user_synonyms` is read RAW, beside the merged `synonyms`, because a suppressed
  // value has no merged entry at all - the published vocabulary must not advertise
  // words for a value it reports as not allowed. Without the raw column the staff words
  // for that value would be absent from this form, and the next save of this key would
  // send a `user_synonyms` that no longer mentions them, deleting them. Suppression is
  // meant to be reversible.
  const wordedValues = dedupe([
    ...(isBoolean ? ['true'] : liveValues),
    ...Object.keys(specKey.synonyms ?? {}),
    ...Object.keys(specKey.user_synonyms ?? {}),
    ...Object.keys(specKey.suppressed_synonyms ?? {}),
  ]);
  const [extraWordRows, setExtraWordRows] = useState<string[]>([]);
  const [newWordRow, setNewWordRow] = useState('');

  // The live words per value, and the shipped ones taken away. Kept apart for the same
  // reason as the values: suppression has to survive a save it was not part of.
  const [words, setWords] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(
      dedupe([...wordedValues]).map((v) => [
        v,
        dedupe([...(specKey.synonyms?.[v] ?? []), ...(specKey.user_synonyms?.[v] ?? [])]),
      ]),
    ),
  );
  const [droppedWords, setDroppedWords] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(
      Object.entries(specKey.suppressed_synonyms ?? {}).map(([v, w]) => [v, [...w]]),
    ),
  );
  const [saving, setSaving] = useState(false);

  const rowValues = dedupe([...wordedValues, ...extraWordRows]);

  const heaviestPreference = Math.max(
    0,
    ...preferences
      .split('\n')
      .map((line) => Number(line.split('=')[1]))
      .filter((n) => Number.isFinite(n)),
  );

  const seedWords = (value: string) => seedWordsFor(specKey, value);

  const removeValue = (value: string) => {
    setLiveValues((current) => current.filter((v) => v !== value));
    // A staff-added value is simply deleted. Only a shipped one leaves a tombstone,
    // because only a shipped one comes back on the next deploy.
    if (seedValues.includes(value)) setDroppedValues((current) => dedupe([...current, value]));
  };

  const restoreValue = (value: string) => {
    setDroppedValues((current) => current.filter((v) => v !== value));
    setLiveValues((current) => dedupe([...current, value]));
  };

  const removeWord = (value: string, word: string) => {
    setWords((current) => ({
      ...current,
      [value]: (current[value] ?? []).filter((w) => w !== word),
    }));
    if (seedWords(value).includes(word)) {
      setDroppedWords((current) => ({
        ...current,
        [value]: dedupe([...(current[value] ?? []), word]),
      }));
    }
  };

  /**
   * Retire a whole value's wording.
   *
   * Shipped words are suppressed rather than deleted, so the row stays on screen with
   * everything struck through and a way back - the same bargain as a single word. A row
   * staff typed themselves just disappears, because there is nothing to come back to.
   */
  const clearWordRow = (value: string) => {
    const seed = seedWords(value);
    setWords((current) => ({ ...current, [value]: [] }));
    if (seed.length > 0) {
      setDroppedWords((current) => ({ ...current, [value]: dedupe([...seed]) }));
    } else {
      setExtraWordRows((current) => current.filter((v) => v !== value));
      setWords((current) => {
        const next = { ...current };
        delete next[value];
        return next;
      });
    }
  };

  const restoreWord = (value: string, word: string) => {
    setDroppedWords((current) => ({
      ...current,
      [value]: (current[value] ?? []).filter((w) => w !== word),
    }));
    setWords((current) => ({ ...current, [value]: dedupe([...(current[value] ?? []), word]) }));
  };

  const save = async () => {
    setSaving(true);
    try {
      // Both payloads are whole lists rather than deltas, and both are worked out in
      // lib/vocabularyEdit so the two ways this went wrong stay under test.
      const { user_synonyms, suppressed_synonyms } = wordPayload(specKey, {
        words: Object.fromEntries(rowValues.map((v) => [v, words[v] ?? []])),
        dropped: droppedWords,
      });
      const { user_values, suppressed_values } = valuePayload(
        specKey,
        liveValues,
        droppedValues,
      );
      const updated = await updateSpecKey(specKey.spec_key, {
        label,
        rank_weight: Number(weight),
        is_active: active,
        match_tolerance: Number(tolerance),
        match_decay: Number(decay),
        user_synonyms,
        suppressed_synonyms,
        excluded_values: excluded,
        derivation_rules: rules,
        // An empty list means "every class". Sent as an absent key rather than an
        // empty array so the stored gate is removed, not stored as a gate that
        // permits nothing.
        applies_when: classScope.length > 0 ? { class: classScope } : {},
        user_values,
        suppressed_values,
        value_weights: Object.fromEntries(
          preferences
            .split('\n')
            .map((line) => line.split('='))
            .filter((parts) => parts.length === 2 && parts[0].trim() && Number(parts[1]))
            .map((parts) => [parts[0].trim(), Number(parts[1])]),
        ),
      });
      // The table row shows the WORDS, not the rules, so editing a rule changes nothing
      // visible. Without this, a successful save and a silent failure look identical.
      toast.success(`${specKey.label} saved`, {
        description:
          rules.length > 0 ? 'Read the catalogue again to apply it to products.' : undefined,
      });
      onSaved(updated);
    } catch (e) {
      // A toast, not an alert at the top of the form: by the time you press Save you
      // have scrolled past the top, and a message you cannot see is a message that did
      // not happen.
      toast.error(e instanceof Error ? e.message : 'Failed to save', { duration: 10_000 });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-md border bg-muted/20 p-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-[12rem] flex-1">
          <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
            What staff call it
          </label>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="w-28">
          <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
            Weight
          </label>
          <Input
            type="number"
            step="0.5"
            min="0"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
          />
        </div>
        {specKey.data_type === 'numeric' && (
          <>
            <div className="w-32">
              <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
                Exact within
              </label>
              <Input
                type="number"
                step="1"
                min="0"
                value={tolerance}
                onChange={(e) => setTolerance(e.target.value)}
              />
            </div>
            <div className="w-32">
              <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
                No match beyond
              </label>
              <Input
                type="number"
                step="10"
                min="0"
                value={decay}
                onChange={(e) => setDecay(e.target.value)}
              />
            </div>
          </>
        )}
        <label className="flex items-center gap-2 text-sm pb-2">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          In use
        </label>
      </div>

      {specKey.data_type === 'enum' && !isOpenVocabulary && (
        <Field
          label="Values this can be"
          hint="Removing one that ships with the product stops this business using it. It stays here, struck through, until you put it back."
        >
          <TokenInput
            values={liveValues}
            muted={seedValues}
            suppressed={droppedValues}
            onRestore={restoreValue}
            onChange={(next) => {
              const removed = liveValues.find((v) => !next.includes(v));
              if (removed) {
                removeValue(removed);
                return;
              }
              const addedValue = next.find((v) => !liveValues.includes(v));
              // Typing back a value that is currently suppressed means "put it back",
              // not "make a second one with the same name".
              if (addedValue && droppedValues.includes(addedValue)) {
                restoreValue(addedValue);
                return;
              }
              setLiveValues(next);
            }}
            normalise={(raw) => raw.trim().toLowerCase().replace(/\s+/g, '_')}
            placeholder="add a value"
            ariaLabel="Values this can be"
          />
        </Field>
      )}

      {specKey.data_type === 'enum' && (
        <Field label="Values nobody searches for">
          <TokenInput
            values={excluded}
            onChange={setExcluded}
            placeholder="add a value"
            ariaLabel="Values nobody searches for"
          />
        </Field>
      )}

      <Field label="Applies to">
        <TokenInput
          values={classScope}
          onChange={setClassScope}
          placeholder={classScope.length === 0 ? 'every class' : 'limit to a class'}
          ariaLabel="Applies to"
        />
      </Field>

      {specKey.read_from === 'product_record' ? (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            How this is read from a product
          </div>
          {/* Reading a column is a rule too. Saying "there are no rules" about the one
              key everybody asks about left the derivation unexplained. */}
          <div className="rounded-md border bg-background p-2 text-sm">
            {ruleSentence(
              { match: 'product_column', pattern: specKey.spec_key },
              specKey.label || specKey.spec_key,
            )}
          </div>
          <span className="text-xs text-muted-foreground">
            Curated data outranks anything parsed out of text, so this rule cannot be
            reordered or switched off here.
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {specKey.rules_are_default && rules.length > 0 && (
            <p className="text-xs text-muted-foreground">
              These {rules.length} rules ship with the product and are what this key is
              read with today. Change one and they become yours - this key stops taking
              future updates to the shipped set.
            </p>
          )}
          {specKey.read_from === 'measurement_then_rules' && (
            <p className="text-xs text-muted-foreground">
              The size written in the product description is read first and always wins.
              These rules fill the gap when it states none - which is how a flyer&apos;s
              &quot;L680xW375xH770mm&quot; gets in. Set a rule&apos;s source to
              &quot;Flyer only&quot; to keep it out of the description.
            </p>
          )}
          <SpecRuleEditor rules={rules} specKey={specKey.spec_key} onChange={setRules} />
        </div>
      )}

      <Field
        label="Prefer these values"
        hint="A standing thumb on the scale, applied whether or not the customer asked for it."
      >
        <textarea
          className="min-h-[4.5rem] w-full rounded-md border border-input bg-background p-2 font-mono text-xs"
          placeholder={'e.g. SORENTO = 1.5'}
          value={preferences}
          onChange={(e) => setPreferences(e.target.value)}
        />
        {/* A preference is meant to reorder answers, not to BE one. Set above a class
            match it silently outranks what the customer actually said: at SORENTO = 8
            every Sorento product beat every Cabana one, so "double bowl kitchen sink"
            returned Sorento sinks with no bowl count over real double-bowl sinks. */}
        {heaviestPreference > CLASS_MATCH_WORTH && (
          <p className="text-xs text-warning">
            {heaviestPreference} is more than a matching product class is worth (
            {CLASS_MATCH_WORTH}), so this preference outranks what the customer asked
            for. Below {CLASS_MATCH_WORTH} it breaks ties instead.
          </p>
        )}
      </Field>

      <Field
        label="Words customers say"
        hint={
          isOpenVocabulary
            ? 'This key has no fixed list of values - whatever the catalogue holds becomes one. Name a value below to give it wording.'
            : undefined
        }
      >
        <div className="flex flex-col gap-2">
          {rowValues.map((value) => (
            <div key={value} className="flex flex-wrap items-start gap-2">
              <span className="flex w-40 shrink-0 items-center gap-1 pt-2 text-sm">
                {/* Struck through exactly as the value itself is in the values section
                    above: the words are kept and stay editable, but until the value is
                    put back the vocabulary carries none of them, and a row that read as
                    live had the two halves of this form disagreeing about one value. */}
                <span
                  className={
                    droppedValues.includes(value)
                      ? 'truncate text-muted-foreground line-through decoration-muted-foreground/60'
                      : 'truncate'
                  }
                >
                  {value === 'true' && isBoolean ? 'When true' : readable(value)}
                </span>
                {/* Clearing a row is the only way to retire a value on a key with no
                    value list of its own - a numeric key's values exist ONLY as these
                    rows, so with no control here a 4 typed by mistake was permanent. */}
                <button
                  type="button"
                  className="cursor-pointer opacity-50 hover:opacity-100"
                  aria-label={`Clear the words for ${value}`}
                  title="Clear this row"
                  onClick={() => clearWordRow(value)}
                >
                  <X className="size-3" />
                </button>
              </span>
              <div className="min-w-[16rem] flex-1">
                <TokenInput
                  values={words[value] ?? []}
                  muted={seedWords(value)}
                  suppressed={droppedWords[value] ?? []}
                  onRestore={(word) => restoreWord(value, word)}
                  onChange={(next) => {
                    const removed = (words[value] ?? []).find((w) => !next.includes(w));
                    if (removed) {
                      removeWord(value, removed);
                      return;
                    }
                    const addedWord = next.find((w) => !(words[value] ?? []).includes(w));
                    if (addedWord && (droppedWords[value] ?? []).includes(addedWord)) {
                      restoreWord(value, addedWord);
                      return;
                    }
                    setWords((c) => ({ ...c, [value]: next }));
                  }}
                  placeholder="add a word"
                  ariaLabel={`Words customers say for ${value}`}
                />
              </div>
            </div>
          ))}

          {(isOpenVocabulary || specKey.data_type === 'numeric') && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Input
                className="w-52"
                value={newWordRow}
                placeholder={specKey.data_type === 'numeric' ? 'a value, e.g. 4' : 'a value, e.g. SORENTO'}
                onChange={(e) => setNewWordRow(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== 'Enter') return;
                  e.preventDefault();
                  const value = newWordRow.trim();
                  if (!value || rowValues.includes(value)) return;
                  setExtraWordRows((current) => [...current, value]);
                  setWords((current) => ({ ...current, [value]: [] }));
                  setNewWordRow('');
                }}
              />
              <span className="text-xs text-muted-foreground">
                Press Enter to give another value its own wording.
              </span>
            </div>
          )}
        </div>
      </Field>

      <div className="flex gap-2">
        <Button onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save specification'}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
