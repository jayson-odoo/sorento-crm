import { readableValue } from '@/lib/spec-readable';
import type {
  SpecCompiledRule,
  SpecRuleBuilder,
  SpecRuleCodeMatch,
  SpecRuleLookIn,
  SpecRuleProductFact,
  SpecRuleSizePick,
  SpecRegistryKey,
} from '../types/productSpec.types';

/**
 * The rule engine's compiler, mirrored from `app/services/product_spec_rules.py`
 * (contract `CONTRACT-product-specs-rule-engine.md`, sections 1-2.1) EXACTLY: every
 * pattern string here has to be valid in both Python `re` and JavaScript `RegExp`, and
 * the two compilers are pinned against one shared fixture of the shipped rules so a
 * drift on either side fails a test rather than a live save.
 *
 * A rule is its `builder` and nothing else (contract 1): nobody types or sees a
 * regular expression. `ruleCells` below turns a builder into the labelled parts the
 * rules grid renders - never a sentence (owner ruling, 27 Sep 2026, "hmm can this be
 * more structured?").
 */

const escapeToken = (token: string) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * One phrase, upper-cased: split on "..." into segments ("anything in between, in the
 * same sentence"), each segment split on runs of spaces/hyphens into tokens (a space,
 * a hyphen or nothing all match between them), each segment bounded by letters only
 * so "LED" never matches inside "SEALED".
 */
function compilePhrase(phrase: string): string {
  const segments = phrase
    .toUpperCase()
    .split('...')
    .map((segment) => segment.trim())
    .filter(Boolean);
  const compiledSegments = segments.map((segment) => {
    const tokens = segment.split(/[\s-]+/).filter(Boolean).map(escapeToken);
    return `(?<![A-Z])${tokens.join('[\\s\\-]*')}(?![A-Z])`;
  });
  return compiledSegments.join('[^.]*?');
}

/** `(?:P1|P2|...)`, in the order given. */
function compileAlternation(phrases: string[]): string {
  return `(?:${phrases.map(compilePhrase).join('|')})`;
}

const STANDALONE_NUMBER = '(\\d+(?:\\.\\d+)?)';
/** A number read BEFORE a word must stand on its own (never the 1008 in SRTKS1008L). */
const NUMBER_GUARD = '(?<![A-Z0-9.])(?<![A-Z0-9]-)';

/** `words` pattern: the alternation, with `\s*$` appended when `at_end`. */
function compileWordsPattern(words: string[], atEnd?: boolean): string {
  return `${compileAlternation(words)}${atEnd ? '\\s*$' : ''}`;
}

/** `number` pattern: before / after / between, per contract section 2. */
function compileNumberPattern(before: string[], after: string[]): string {
  const hasBefore = before.length > 0;
  const hasAfter = after.length > 0;
  const w = hasBefore ? compileAlternation(before) : '';
  const a = hasAfter ? compileAlternation(after) : '';
  if (hasAfter && hasBefore) {
    return `${a}[\\s\\-:,]*${STANDALONE_NUMBER}[\\s\\-]*${w}(?![A-Z])`;
  }
  if (hasAfter) {
    return `${a}[\\s\\-:,]*${STANDALONE_NUMBER}`;
  }
  return `${NUMBER_GUARD}${STANDALONE_NUMBER}[\\s\\-]*${w}(?![A-Z])`;
}

const SIZE_PART = '(?:([LWHD])\\s*)?(\\d+(?:\\.\\d+)?)\\s*(?:MM)?';
/** The size regex, 2 to 4 labelled-or-not parts (contract section 2). */
export const SIZE_PATTERN =
  `${SIZE_PART}\\s*[X*]\\s*${SIZE_PART}` +
  `(?:\\s*[X*]\\s*${SIZE_PART})?` +
  `(?:\\s*[X*]\\s*${SIZE_PART})?`;

/** `skip_after`: searched against the text before a hit; a match skips that hit. */
function compileSkip(skipAfter: string[] | undefined): string | null {
  if (!skipAfter || skipAfter.length === 0) return null;
  return `(?<![A-Z])${compileAlternation(skipAfter)}[\\s\\-:,(]*$`;
}

const WRITTEN_IN_SCALE: Record<'centimetres' | 'metres', number> = {
  centimetres: 10,
  metres: 1000,
};

/** `compile_builder(builder)` - what the engine and Try it run (contract 2.1). */
export function compileBuilder(builder: SpecRuleBuilder): SpecCompiledRule {
  const base: SpecCompiledRule = {
    kind: builder.kind,
    scope: null,
    pattern: null,
    capture: null,
    skip: null,
    scale: null,
    min: null,
    pick: null,
    code_match: null,
    texts: null,
    fact: null,
  };

  switch (builder.kind) {
    case 'words':
      return {
        ...base,
        // `scope` is `look_in`, or null when absent - the caller (or the server's
        // own default) decides what an absent look_in means for this spec (contract
        // 1.1: "name" for Product class, "any" for everything else).
        scope: builder.look_in ?? null,
        pattern: compileWordsPattern(builder.words ?? [], builder.at_end),
        skip: compileSkip(builder.skip_after),
      };
    case 'number':
      return {
        ...base,
        scope: builder.look_in ?? null,
        pattern: compileNumberPattern(builder.before ?? [], builder.after ?? []),
        capture: 1,
        skip: compileSkip(builder.skip_after),
        scale: builder.written_in ? WRITTEN_IN_SCALE[builder.written_in] : null,
        min: builder.ignore_below ?? null,
      };
    case 'size':
      return {
        ...base,
        scope: builder.look_in ?? null,
        pattern: SIZE_PATTERN,
        pick: builder.pick,
      };
    case 'code':
      return {
        ...base,
        scope: 'code',
        code_match: builder.code_match,
        texts: (builder.texts ?? []).map((t) => t.toUpperCase()),
      };
    case 'product':
      return {
        ...base,
        scope: 'product',
        fact: builder.fact,
      };
    default:
      return base;
  }
}

// --- The rules grid's cells (D14): labelled parts, never a sentence -------------

const LOOK_IN_LABEL: Record<SpecRuleLookIn, string> = {
  any: 'Description or flyer',
  description: 'Description only',
  flyer: 'Flyer only',
  name: 'The product name',
};

const CODE_MATCH_LABEL: Record<SpecRuleCodeMatch, string> = {
  contains: 'Contains',
  starts_with: 'Starts with',
  ends_with: 'Ends with',
};

const PRODUCT_FACT_LABEL: Record<SpecRuleProductFact, string> = {
  class: "The product's category's class",
  name: "What the product's name says it is",
  length: "The product's length",
  width: "The product's width",
  height: "The product's height",
};

function sizePickLabel(pick: SpecRuleSizePick): string {
  if (pick === 'L' || pick === 'W' || pick === 'H') return `Labelled: ${pick}`;
  const suffix = pick === 1 ? 'st' : pick === 2 ? 'nd' : pick === 3 ? 'rd' : 'th';
  return `${pick}${suffix} number`;
}

/** "Where to look" cell (AC-S1.14): Code and Product rules read their own place. */
export function whereToLookCell(builder: SpecRuleBuilder, specKey?: string): string {
  if (builder.kind === 'code') return 'Product code';
  if (builder.kind === 'product') return 'The product';
  const fallback: SpecRuleLookIn = specKey === 'class' ? 'name' : 'any';
  return LOOK_IN_LABEL[builder.look_in ?? fallback];
}

const KIND_LABEL: Record<SpecRuleBuilder['kind'], string> = {
  words: 'Words',
  number: 'Number',
  size: 'Size',
  code: 'Code',
  product: 'Product',
};

export function kindCell(builder: SpecRuleBuilder): string {
  return KIND_LABEL[builder.kind];
}

/** "What to find" cell: the primary line and any optional second-line parts. */
export function whatToFindCell(builder: SpecRuleBuilder): { primary: string; secondary: string[] } {
  switch (builder.kind) {
    case 'words': {
      const secondary: string[] = [];
      if (builder.at_end) secondary.push('Only at the end');
      if (builder.skip_after?.length) secondary.push(`Skip after: ${builder.skip_after.join(', ')}`);
      return { primary: builder.words.join(', '), secondary };
    }
    case 'number': {
      const parts: string[] = [];
      if (builder.after?.length) parts.push(`After: ${builder.after.join(', ')}`);
      if (builder.before?.length) parts.push(`Before: ${builder.before.join(', ')}`);
      const secondary: string[] = [];
      if (builder.skip_after?.length) secondary.push(`Skip after: ${builder.skip_after.join(', ')}`);
      if (builder.written_in) secondary.push(`Written in: ${builder.written_in}`);
      if (builder.ignore_below !== undefined && builder.ignore_below !== null) {
        secondary.push(`Ignore below: ${builder.ignore_below}`);
      }
      return { primary: parts.join(' · '), secondary };
    }
    case 'size':
      return { primary: sizePickLabel(builder.pick), secondary: [] };
    case 'code':
      return {
        primary: `${CODE_MATCH_LABEL[builder.code_match]}: ${builder.texts.join(', ')}`,
        secondary: [],
      };
    case 'product':
      return { primary: PRODUCT_FACT_LABEL[builder.fact], secondary: [] };
    default:
      return { primary: '', secondary: [] };
  }
}

/** "Value it sets" cell: the spec's own choice label, or "The number it finds". */
export function valueItSetsCell(builder: SpecRuleBuilder, spec?: SpecRegistryKey): string {
  if (builder.kind === 'number' || builder.kind === 'size' || builder.kind === 'product') {
    return 'The number it finds';
  }
  const value = builder.value;
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  return readableValue(value, undefined, spec?.value_labels);
}

/** "Only when" cell: "Shape is not: Round, Square", or blank. */
export function onlyWhenCell(
  builder: SpecRuleBuilder,
  lookupSpec?: (specKey: string) => SpecRegistryKey | undefined,
): string {
  const onlyWhen = builder.only_when;
  if (!onlyWhen) return '';
  const other = lookupSpec?.(onlyWhen.spec);
  const label = other?.label ?? onlyWhen.spec;
  const values = onlyWhen.values
    .map((value) => readableValue(value, undefined, other?.value_labels))
    .join(', ');
  return `${label} is${onlyWhen.is === false ? ' not' : ''}: ${values}`;
}

/** Every rules-grid column for one rule, in one call (D14). */
export function ruleCells(
  builder: SpecRuleBuilder,
  spec?: SpecRegistryKey,
  lookupSpec?: (specKey: string) => SpecRegistryKey | undefined,
): {
  whereToLook: string;
  kind: string;
  whatToFind: { primary: string; secondary: string[] };
  valueItSets: string;
  onlyWhen: string;
} {
  return {
    whereToLook: whereToLookCell(builder, spec?.spec_key),
    kind: kindCell(builder),
    whatToFind: whatToFindCell(builder),
    valueItSets: valueItSetsCell(builder, spec),
    onlyWhen: onlyWhenCell(builder, lookupSpec),
  };
}
