'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { readableValue } from '@/lib/spec-readable';
import { toast } from '@/lib/toast';
import { compileBuilder, ruleCells } from '../lib/ruleSentence';
import SpecTryItPanel from './SpecTryItPanel';
import SpecPreviewPanel from './SpecPreviewPanel';
import { useSpecTryIt, type TryItSource } from '../hooks/useSpecTryIt';
import type {
  SpecDerivationRule,
  SpecRegistryKey,
  SpecRuleBuilder,
  SpecRuleCodeMatch,
  SpecRuleKind,
  SpecRuleLookIn,
  SpecRuleProductFact,
  SpecRuleSizePick,
  SpecRuleWrittenIn,
} from '../types/productSpec.types';

const KIND_OPTIONS: { value: SpecRuleKind; label: string }[] = [
  { value: 'words', label: 'Words' },
  { value: 'number', label: 'Number' },
  { value: 'size', label: 'Size' },
  { value: 'code', label: 'Code' },
  { value: 'product', label: 'Product' },
];

const LOOK_IN_OPTIONS: { value: SpecRuleLookIn; label: string }[] = [
  { value: 'any', label: 'Description or flyer' },
  { value: 'description', label: 'Description only' },
  { value: 'flyer', label: 'Flyer only' },
  { value: 'name', label: 'The product name' },
];

const NUMBER_MODE_OPTIONS = [
  { value: 'before', label: 'before' },
  { value: 'after', label: 'after' },
  { value: 'between', label: 'between' },
];

const SIZE_PICK_OPTIONS: { value: string; label: string }[] = [
  { value: '1', label: '1st (length)' },
  { value: '2', label: '2nd (width)' },
  { value: '3', label: '3rd (height)' },
  { value: '4', label: '4th (thickness)' },
  { value: 'L', label: 'the one labelled L' },
  { value: 'W', label: 'the one labelled W' },
  { value: 'H', label: 'the one labelled H' },
];

const CODE_MATCH_OPTIONS: { value: SpecRuleCodeMatch; label: string }[] = [
  { value: 'contains', label: 'contains' },
  { value: 'starts_with', label: 'starts with' },
  { value: 'ends_with', label: 'ends with' },
];

const PRODUCT_FACT_OPTIONS: { value: SpecRuleProductFact; label: string }[] = [
  { value: 'class', label: "its category's class" },
  { value: 'name', label: "what its name says it is" },
  { value: 'length', label: "its length" },
  { value: 'width', label: "its width" },
  { value: 'height', label: "its height" },
];

const WRITTEN_IN_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'as stored (mm)' },
  { value: 'centimetres', label: 'centimetres' },
  { value: 'metres', label: 'metres' },
];

const toUpperList = (list: string[]) =>
  Array.from(new Set(list.map((w) => w.trim().toUpperCase()).filter(Boolean)));

/** The mutable form shape, one field per part across every kind (plan D5). */
interface RuleDraft {
  kind: SpecRuleKind;
  look_in: SpecRuleLookIn | '';
  words: string[];
  at_end: boolean;
  skip_after: string[];
  value: string;
  number_mode: 'before' | 'after' | 'between';
  before: string[];
  after: string[];
  written_in: SpecRuleWrittenIn;
  ignore_below: string;
  pick: SpecRuleSizePick;
  code_match: SpecRuleCodeMatch;
  texts: string[];
  fact: SpecRuleProductFact;
  only_when_spec: string;
  only_when_is: 'is' | 'is_not';
  only_when_values: string[];
}

function draftFromBuilder(builder: SpecRuleBuilder | null): RuleDraft {
  const base: RuleDraft = {
    kind: builder?.kind ?? 'words',
    look_in: (builder && 'look_in' in builder ? builder.look_in : undefined) ?? '',
    words: [],
    at_end: false,
    skip_after: [],
    value: '',
    number_mode: 'before',
    before: [],
    after: [],
    written_in: null,
    ignore_below: '',
    pick: 1,
    code_match: 'ends_with',
    texts: [],
    fact: 'length',
    only_when_spec: '',
    only_when_is: 'is',
    only_when_values: [],
  };
  if (!builder) return base;
  if (builder.only_when) {
    base.only_when_spec = builder.only_when.spec;
    base.only_when_is = builder.only_when.is === false ? 'is_not' : 'is';
    base.only_when_values = builder.only_when.values;
  }
  switch (builder.kind) {
    case 'words':
      return {
        ...base,
        words: builder.words,
        at_end: !!builder.at_end,
        skip_after: builder.skip_after ?? [],
        value: builder.value === true ? 'true' : String(builder.value ?? ''),
      };
    case 'number':
      return {
        ...base,
        before: builder.before ?? [],
        after: builder.after ?? [],
        number_mode:
          (builder.before?.length ?? 0) > 0 && (builder.after?.length ?? 0) > 0
            ? 'between'
            : (builder.after?.length ?? 0) > 0
              ? 'after'
              : 'before',
        written_in: builder.written_in ?? null,
        ignore_below:
          builder.ignore_below === null || builder.ignore_below === undefined
            ? ''
            : String(builder.ignore_below),
        skip_after: builder.skip_after ?? [],
      };
    case 'size':
      return { ...base, pick: builder.pick };
    case 'code':
      return {
        ...base,
        code_match: builder.code_match,
        texts: builder.texts,
        value: builder.value === true ? 'true' : String(builder.value ?? ''),
      };
    case 'product':
      return { ...base, fact: builder.fact };
    default:
      return base;
  }
}

/** The value it sets, coerced from the free-text/select input back to what the
 *  builder stores: a number for a Number spec, `true` for Yes or no, the choice
 *  key otherwise. */
function coerceValue(spec: SpecRegistryKey, raw: string): string | number | boolean {
  if (spec.data_type === 'boolean') return true;
  if (spec.data_type === 'numeric') {
    const n = Number(raw);
    return Number.isFinite(n) ? n : raw;
  }
  return raw;
}

function buildBuilder(draft: RuleDraft, spec: SpecRegistryKey): SpecRuleBuilder | null {
  const onlyWhen =
    draft.only_when_spec && draft.only_when_values.length > 0
      ? {
          spec: draft.only_when_spec,
          is: draft.only_when_is === 'is',
          values: draft.only_when_values,
        }
      : undefined;

  switch (draft.kind) {
    case 'words': {
      const words = toUpperList(draft.words);
      if (words.length === 0) return null;
      return {
        kind: 'words',
        look_in: draft.look_in || undefined,
        words,
        at_end: draft.at_end || undefined,
        skip_after: draft.skip_after.length ? toUpperList(draft.skip_after) : undefined,
        value: coerceValue(spec, draft.value),
        only_when: onlyWhen,
      };
    }
    case 'number': {
      const before = draft.number_mode !== 'after' ? toUpperList(draft.before) : [];
      const after = draft.number_mode !== 'before' ? toUpperList(draft.after) : [];
      if (before.length === 0 && after.length === 0) return null;
      const ignoreBelow = draft.ignore_below.trim() === '' ? null : Number(draft.ignore_below);
      return {
        kind: 'number',
        look_in: draft.look_in || undefined,
        before: before.length ? before : undefined,
        after: after.length ? after : undefined,
        written_in: draft.written_in ?? undefined,
        ignore_below: Number.isFinite(ignoreBelow) ? ignoreBelow : null,
        skip_after: draft.skip_after.length ? toUpperList(draft.skip_after) : undefined,
        only_when: onlyWhen,
      };
    }
    case 'size':
      return { kind: 'size', look_in: draft.look_in || undefined, pick: draft.pick, only_when: onlyWhen };
    case 'code': {
      const texts = toUpperList(draft.texts);
      if (texts.length === 0) return null;
      return {
        kind: 'code',
        code_match: draft.code_match,
        texts,
        value: coerceValue(spec, draft.value),
        only_when: onlyWhen,
      };
    }
    case 'product':
      return { kind: 'product', fact: draft.fact, only_when: onlyWhen };
    default:
      return null;
  }
}

/** The rule as the one grid row it will become - never a sentence (AC-S1.7). */
function RulePreviewRow({
  builder,
  spec,
  lookupSpec,
}: {
  builder: SpecRuleBuilder | null;
  spec: SpecRegistryKey;
  lookupSpec: (specKey: string) => SpecRegistryKey | undefined;
}) {
  if (!builder) {
    return (
      <p className="text-sm text-muted-foreground">
        Fill in the fields above to see the rule it becomes.
      </p>
    );
  }
  const cells = ruleCells(builder, spec, lookupSpec);
  return (
    <div className="overflow-hidden rounded-md border">
      <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead className="bg-muted/40 text-xs text-muted-foreground">
          <tr>
            <th className="p-2 text-left font-medium">Where to look</th>
            <th className="p-2 text-left font-medium">Kind</th>
            <th className="p-2 text-left font-medium">What to find</th>
            <th className="p-2 text-left font-medium">Value it sets</th>
            <th className="p-2 text-left font-medium">Only when</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="p-2">{cells.whereToLook}</td>
            <td className="p-2">{cells.kind}</td>
            <td className="p-2">
              <div className="font-medium">{cells.whatToFind.primary || '-'}</div>
              {cells.whatToFind.secondary.map((line) => (
                <div key={line} className="text-xs text-muted-foreground">
                  {line}
                </div>
              ))}
            </td>
            <td className="p-2">{cells.valueItSets}</td>
            <td className="p-2 text-muted-foreground">{cells.onlyWhen || '-'}</td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>
  );
}

export interface SpecRuleModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  spec: SpecRegistryKey;
  /** The full registry, so "Only when" can pick any other spec. */
  registry: SpecRegistryKey[];
  /** The draft grid as it stands; the edited/new rule replaces its own slot for
   *  Try it / See what would change. */
  rules: SpecDerivationRule[];
  /** null = editing rule at this index; the index is -1 for a brand new rule. */
  editingIndex: number | null;
  onSave: (rule: SpecDerivationRule, index: number | null) => void;
}

/**
 * Add a rule / Edit (AC-S1.7, AC-S1.8, AC-S1.18): the grid's own parts, in the
 * grid's own order, every pick a `SearchableSelect` or `SearchableMultiSelect`. No
 * sentence anywhere - the fields are previewed as the one grid row they become.
 */
export function SpecRuleModal({
  open,
  onOpenChange,
  spec,
  registry,
  rules,
  editingIndex,
  onSave,
}: SpecRuleModalProps) {
  const existing = editingIndex !== null ? (rules[editingIndex]?.builder ?? null) : null;
  const [draft, setDraft] = useState<RuleDraft>(() => draftFromBuilder(existing));
  const [trySource, setTrySource] = useState<TryItSource | null>(null);

  useEffect(() => {
    if (open) {
      setDraft(draftFromBuilder(existing));
      setTrySource(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editingIndex]);

  const lookupSpec = useMemo(
    () => (specKey: string) => registry.find((k) => k.spec_key === specKey),
    [registry],
  );

  const builder = useMemo(() => buildBuilder(draft, spec), [draft, spec]);

  const draftRules = useMemo<SpecDerivationRule[]>(() => {
    if (!builder) return rules;
    const compiled = compileBuilder(builder);
    const asRule: SpecDerivationRule = { builder, pattern: compiled.pattern };
    if (editingIndex === null) return [...rules, asRule];
    return rules.map((r, i) => (i === editingIndex ? asRule : r));
  }, [builder, rules, editingIndex]);

  const { result: tryResult, loading: tryLoading, error: tryError } = useSpecTryIt(
    spec.spec_key,
    builder ? [{ builder, pattern: compileBuilder(builder).pattern }] : [],
    trySource,
  );

  const wordChoices = useMemo(() => {
    const known = new Set<string>();
    for (const rule of rules) {
      if (rule.builder?.kind === 'words') rule.builder.words.forEach((w) => known.add(w));
    }
    Object.values(spec.synonyms ?? {}).forEach((words) => words.forEach((w) => known.add(w.toUpperCase())));
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

  const onlyWhenSpecOptions = useMemo(
    () =>
      registry
        .filter((k) => k.spec_key !== spec.spec_key && k.spec_key !== 'brand')
        .map((k) => ({ value: k.spec_key, label: k.label })),
    [registry, spec.spec_key],
  );
  const onlyWhenValueOptions = useMemo(() => {
    const other = lookupSpec(draft.only_when_spec);
    if (!other) return [];
    return other.allowed_values.map((value) => ({
      value,
      label: readableValue(value, undefined, other.value_labels),
    }));
  }, [draft.only_when_spec, lookupSpec]);

  const wordsMultiSelect = (
    value: string[],
    onChange: (next: string[]) => void,
    placeholder: string,
  ) => (
    <SearchableMultiSelect
      value={value}
      onChange={onChange}
      options={wordChoices.map((w) => ({ value: w, label: w }))}
      placeholder={placeholder}
      emptyMessage="No words yet."
      createOption={{
        label: (query) => <span>Add &ldquo;{query.toUpperCase()}&rdquo;</span>,
        onCreate: (query) => onChange(toUpperList([...value, query])),
      }}
    />
  );

  const hideWhereToLook = draft.kind === 'code' || draft.kind === 'product';
  const hideValueItSets = draft.kind === 'number' || draft.kind === 'size' || draft.kind === 'product';

  const save = () => {
    if (!builder) {
      toast.error(
        draft.kind === 'words'
          ? 'Add at least one word to find.'
          : draft.kind === 'number'
            ? 'Add at least one word next to the number.'
            : draft.kind === 'code'
              ? 'Add at least one piece of code to find.'
              : 'Fill in what this rule reads.',
      );
      return;
    }
    const compiled = compileBuilder(builder);
    onSave({ builder, pattern: compiled.pattern }, editingIndex);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {editingIndex !== null ? `Edit a rule for ${spec.label}` : `Add a rule to ${spec.label}`}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {!hideWhereToLook && (
            <div className="flex flex-col gap-1.5">
              <Label>Where to look</Label>
              <SearchableSelect
                value={draft.look_in || (spec.spec_key === 'class' ? 'name' : 'any')}
                onChange={(value) => setDraft((d) => ({ ...d, look_in: value as SpecRuleLookIn }))}
                options={LOOK_IN_OPTIONS}
              />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label>Kind</Label>
            <SearchableSelect
              value={draft.kind}
              onChange={(value) => setDraft(() => ({ ...draftFromBuilder(null), kind: value as SpecRuleKind }))}
              options={KIND_OPTIONS}
            />
          </div>

          {draft.kind === 'words' && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label>What to find</Label>
                {wordsMultiSelect(draft.words, (words) => setDraft((d) => ({ ...d, words })), 'Words this spec should read')}
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={draft.at_end}
                  onCheckedChange={(checked) => setDraft((d) => ({ ...d, at_end: !!checked }))}
                  id="rule-at-end"
                />
                <Label htmlFor="rule-at-end" className="text-sm font-normal">
                  Only at the end of the product name
                </Label>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Skip it when it comes right after some words</Label>
                {wordsMultiSelect(draft.skip_after, (skip_after) => setDraft((d) => ({ ...d, skip_after })), 'Optional')}
              </div>
            </>
          )}

          {draft.kind === 'number' && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label>The number</Label>
                <SearchableSelect
                  value={draft.number_mode}
                  onChange={(value) => setDraft((d) => ({ ...d, number_mode: value as RuleDraft['number_mode'] }))}
                  options={NUMBER_MODE_OPTIONS}
                />
              </div>
              {draft.number_mode !== 'before' && (
                <div className="flex flex-col gap-1.5">
                  <Label>After</Label>
                  {wordsMultiSelect(draft.after, (after) => setDraft((d) => ({ ...d, after })), 'Words the number comes after')}
                </div>
              )}
              {draft.number_mode !== 'after' && (
                <div className="flex flex-col gap-1.5">
                  <Label>Before</Label>
                  {wordsMultiSelect(draft.before, (before) => setDraft((d) => ({ ...d, before })), 'Words the number comes before')}
                </div>
              )}
              <div className="flex flex-col gap-1.5">
                <Label>Written in</Label>
                <SearchableSelect
                  value={draft.written_in ?? ''}
                  onChange={(value) =>
                    setDraft((d) => ({ ...d, written_in: (value || null) as SpecRuleWrittenIn }))
                  }
                  options={WRITTEN_IN_OPTIONS}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Ignore numbers below</Label>
                <Input
                  type="number"
                  className="w-40"
                  value={draft.ignore_below}
                  onChange={(e) => setDraft((d) => ({ ...d, ignore_below: e.target.value }))}
                  placeholder="no floor"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Skip it when it comes right after some words</Label>
                {wordsMultiSelect(draft.skip_after, (skip_after) => setDraft((d) => ({ ...d, skip_after })), 'Optional')}
              </div>
            </>
          )}

          {draft.kind === 'size' && (
            <div className="flex flex-col gap-1.5">
              <Label>Take</Label>
              <SearchableSelect
                value={String(draft.pick)}
                onChange={(value) =>
                  setDraft((d) => ({
                    ...d,
                    pick: (['L', 'W', 'H'].includes(value) ? value : Number(value)) as SpecRuleSizePick,
                  }))
                }
                options={SIZE_PICK_OPTIONS}
              />
            </div>
          )}

          {draft.kind === 'code' && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label>The code</Label>
                <SearchableSelect
                  value={draft.code_match}
                  onChange={(value) => setDraft((d) => ({ ...d, code_match: value as SpecRuleCodeMatch }))}
                  options={CODE_MATCH_OPTIONS}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Text</Label>
                {wordsMultiSelect(draft.texts, (texts) => setDraft((d) => ({ ...d, texts })), 'Piece of the product code')}
              </div>
            </>
          )}

          {draft.kind === 'product' && (
            <div className="flex flex-col gap-1.5">
              <Label>Use</Label>
              <SearchableSelect
                value={draft.fact}
                onChange={(value) => setDraft((d) => ({ ...d, fact: value as SpecRuleProductFact }))}
                options={PRODUCT_FACT_OPTIONS}
              />
            </div>
          )}

          {!hideValueItSets && (
            <div className="flex flex-col gap-1.5">
              <Label>Value it sets</Label>
              {spec.data_type === 'boolean' ? (
                <Input value="Yes" disabled className="w-40" />
              ) : spec.data_type === 'numeric' ? (
                <Input
                  type="number"
                  className="w-40"
                  value={draft.value}
                  onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))}
                />
              ) : (
                <SearchableSelect
                  value={draft.value}
                  onChange={(value) => setDraft((d) => ({ ...d, value }))}
                  options={valueOptions}
                  clearable
                  placeholder="Pick a choice"
                />
              )}
            </div>
          )}

          <div className="flex flex-col gap-1.5 rounded-md border p-3">
            <Label>Only when (optional)</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <SearchableSelect
                value={draft.only_when_spec}
                onChange={(value) =>
                  setDraft((d) => ({ ...d, only_when_spec: value, only_when_values: [] }))
                }
                options={onlyWhenSpecOptions}
                clearable
                placeholder="Another specification"
                triggerClassName="sm:w-56"
              />
              <SearchableSelect
                value={draft.only_when_is}
                onChange={(value) => setDraft((d) => ({ ...d, only_when_is: value as 'is' | 'is_not' }))}
                options={[
                  { value: 'is', label: 'is' },
                  { value: 'is_not', label: 'is not' },
                ]}
                disabled={!draft.only_when_spec}
                triggerClassName="sm:w-28"
              />
              <SearchableMultiSelect
                value={draft.only_when_values}
                onChange={(values) => setDraft((d) => ({ ...d, only_when_values: values }))}
                options={onlyWhenValueOptions}
                disabled={!draft.only_when_spec}
                placeholder="Its values"
                triggerClassName="sm:flex-1"
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>This rule in the grid</Label>
            <RulePreviewRow builder={builder} spec={spec} lookupSpec={lookupSpec} />
          </div>

          <SpecTryItPanel
            source={trySource}
            onSourceChange={setTrySource}
            description={tryResult?.description ?? null}
            loading={tryLoading}
            error={tryError}
          />
          {trySource && !tryLoading && (
            <p className="text-sm">
              {tryResult?.reads?.[0]?.value === null || tryResult?.reads?.[0]?.value === undefined
                ? 'Reads nothing.'
                : `Reads ${readableValue(tryResult.reads[0].value, undefined, spec.value_labels)}.`}
            </p>
          )}

          <SpecPreviewPanel specKey={spec.spec_key} rules={draftRules} />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save}>Save rule</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SpecRuleModal;
