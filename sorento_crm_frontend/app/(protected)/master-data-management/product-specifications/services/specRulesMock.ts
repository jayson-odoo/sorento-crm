import type {
  SpecDerivationRule,
  SpecPreviewJobResult,
  SpecPreviewSampleRow,
  SpecTryResult,
  SpecTryRuleRead,
} from '../types/productSpec.types';
import { compileBuilder } from '../lib/ruleSentence';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

/**
 * The Phase 1 stand-in for the try/preview endpoints (AC-B.1, B.2), which do not exist
 * on the backend until S3. Deleting this file and the `USE_MOCK` branch in
 * `productSpecService.ts` is the whole S3 swap - nothing in a component or hook changes,
 * because both already call the service, never this module directly.
 *
 * Try-it here is a GENUINE compile-and-match: every row is compiled (via `compileBuilder`
 * for a builder row, or read as-is for a pattern row) and run against the description/code
 * text in JS, in order, exactly the way the real engine would. `from_field` and
 * `name_head` are the two exceptions - one reads the product record, the other runs a
 * multi-step text transform - and produce a canned read rather than a genuine one, same
 * as `compileBuilder`'s Advanced-pane pattern for them is illustrative, not executable.
 */

const READ_DELAY_MS = 250;
const PREVIEW_DELAY_MS = 1_500;

function delay<T>(value: T, ms: number): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

/** A compiled rule's engine fields, whichever way they were arrived at. */
type CompiledRule = Pick<
  SpecDerivationRule,
  'match' | 'pattern' | 'capture' | 'value'
>;

function compiledFieldsOf(rule: SpecDerivationRule): CompiledRule {
  return rule.builder ? compileBuilder(rule.builder) : rule;
}

/** text before the first bracket or WITH/C/W/FOR/W/ tail, mirroring `class_text` closely
 *  enough for a demo read - not the code the engine actually runs (S2 owns that). */
function nameHeadRead(
  text: string,
): { value: string; evidence: string } | null {
  if (!text.trim()) return null;
  let head = text.toUpperCase();
  const cut = head.search(/\(|\bWITH\b|\bC\/W\b|\bFOR\b|\bW\/\b/);
  if (cut > 0) head = head.slice(0, cut);
  head = head.replace(/[\d.]+\s*X\s*[\d.]+.*$/i, '').trim();
  if (!head) return null;
  return { value: head, evidence: head };
}

/** `from_field` reads the product record, which Phase 1's mock does not carry - a fixed
 *  read stands in until S2 wires the real column/category/brand lookup. */
function fromFieldRead(field: string): {
  value: string | number;
  evidence: string;
} {
  if (field === 'category')
    return { value: 'basin', evidence: "the product's category" };
  if (field === 'brand')
    return { value: 'sorento', evidence: "the product's brand field" };
  if (field.startsWith('column:')) {
    const column = field.slice('column:'.length);
    return { value: 700, evidence: `the product's ${column} column` };
  }
  return { value: field, evidence: `the product's ${field} field` };
}

function readOne(
  compiled: CompiledRule,
  text: string,
  code: string,
): { value: string | number | boolean; evidence: string } | null {
  const pattern = compiled.pattern ?? '';
  if (!pattern) return null;

  switch (compiled.match) {
    case 'regex': {
      let re: RegExp;
      try {
        re = new RegExp(pattern, 'i');
      } catch {
        return null;
      }
      const m = re.exec(text);
      if (!m) return null;
      if (compiled.capture !== undefined) {
        const raw = m[compiled.capture];
        if (raw === undefined) return null;
        const num = Number(raw);
        return {
          value: Number.isFinite(num) && raw.trim() !== '' ? num : raw,
          evidence: m[0].trim(),
        };
      }
      return { value: compiled.value ?? true, evidence: m[0].trim() };
    }
    case 'contains': {
      const needle = pattern.toUpperCase();
      if (!text.toUpperCase().includes(needle)) return null;
      return {
        value: compiled.value === '' ? true : (compiled.value ?? true),
        evidence: pattern,
      };
    }
    case 'ends_with': {
      const needle = pattern.toUpperCase();
      if (!text.toUpperCase().trim().endsWith(needle)) return null;
      return {
        value: compiled.value === '' ? true : (compiled.value ?? true),
        evidence: pattern,
      };
    }
    case 'present': {
      const needle = pattern.toUpperCase();
      if (!text.toUpperCase().includes(needle)) return null;
      return { value: 'yes', evidence: pattern };
    }
    case 'code_contains': {
      const needle = pattern.toUpperCase();
      if (!code.toUpperCase().includes(needle)) return null;
      return {
        value: compiled.value === '' ? pattern : (compiled.value ?? pattern),
        evidence: pattern,
      };
    }
    case 'code_starts_with': {
      const needle = pattern.toUpperCase();
      if (!code.toUpperCase().startsWith(needle)) return null;
      return {
        value: compiled.value === '' ? pattern : (compiled.value ?? pattern),
        evidence: pattern,
      };
    }
    case 'code_suffix': {
      const needle = pattern.toUpperCase();
      if (!code.toUpperCase().endsWith(needle)) return null;
      return {
        value: compiled.value === '' ? pattern : (compiled.value ?? pattern),
        evidence: pattern,
      };
    }
    case 'from_field':
      return fromFieldRead(pattern);
    default:
      return null;
  }
}

/** Compile and run every row against one text/code pair, in order - the same order the
 *  engine reads it in, so the first row with a value is the winner. */
export function computeReads(
  rules: SpecDerivationRule[],
  text: string,
  code: string,
): { reads: SpecTryRuleRead[]; winnerIndex: number | null } {
  let winnerIndex: number | null = null;
  const reads = rules.map((rule, index) => {
    const read =
      rule.builder?.kind === 'name_head'
        ? nameHeadRead(text)
        : readOne(compiledFieldsOf(rule), text, code);
    if (read && winnerIndex === null) winnerIndex = index;
    return {
      index,
      value: read?.value ?? null,
      evidence: read?.evidence ?? null,
    };
  });
  return { reads, winnerIndex };
}

// --- Canned product descriptions, keyed by the picked option's label ----------------
//
// The real try endpoint (S3) reads the product's actual description server-side.
// Phase 1's picker only has an id/label from the products/select dropdown, which does
// not return description text, so a picked product's "description" here is a small
// canned table keyed by what is in the label - good enough to exercise every render
// path (a match, no match, a winner) without a live description field to read.
const CANNED_DESCRIPTIONS: { test: RegExp; description: string }[] = [
  {
    test: /8354/,
    description:
      'SRTWC8354-SH-P WASH DOWN CLOSE COUPLED WATER CLOSET S-TRAP:300MM',
  },
  {
    test: /basin/i,
    description: 'MARBLE TOP BASIN (800MM)',
  },
  {
    test: /sink/i,
    description:
      'STAINLESS STEEL KITCHEN SINK L1000 x W500 x H200mm SINGLE BOWL',
  },
];

export function mockDescriptionFor(label: string): string {
  const found = CANNED_DESCRIPTIONS.find((c) => c.test.test(label));
  if (found) return found.description;
  const parts = label.split(' - ');
  return (parts.length > 1 ? parts.slice(1).join(' - ') : label).toUpperCase();
}

export function mockCodeFor(label: string): string {
  return label.split(' - ')[0]?.trim() ?? label;
}

/** Used only when the real products/select endpoint cannot be reached (no backend, or a
 *  network error) - the picker still opens in fetchOptions mode rather than looking dead. */
export const PRODUCT_PICKER_FALLBACK: SearchableSelectOption[] = [
  {
    value: 'mock-srtwc8354',
    label: 'SRTWC8354-SH-P - Wash down close coupled water closet',
  },
  { value: 'mock-basin-800', label: 'SRTBA800 - Marble top basin 800mm' },
  {
    value: 'mock-sink-1000',
    label: 'SRTSK1000 - Stainless steel kitchen sink single bowl',
  },
];

export async function mockTrySpecRules(
  rules: SpecDerivationRule[],
  source: { text: string; code: string },
): Promise<SpecTryResult> {
  const { reads, winnerIndex } = computeReads(rules, source.text, source.code);
  return delay(
    { description: source.text, reads, winner_index: winnerIndex },
    READ_DELAY_MS,
  );
}

let mockJobSeq = 0;

export async function mockPreviewSpecRules(): Promise<{ jobId: string }> {
  mockJobSeq += 1;
  return delay({ jobId: `mock-preview-${mockJobSeq}` }, 50);
}

const MOCK_SAMPLE_CODES = [
  'SRTWB101',
  'SRTWB102-BL',
  'SRTWC201',
  'SRTWC202-CR',
  'SRTBA301',
  'SRTBA302-WH',
  'SRTSK401',
  'SRTSK402',
  'SRTFT501-GM',
  'SRTFT502',
  'SRTSH601',
  'SRTSH602-NK',
  'SRTAC701',
  'SRTAC702',
  'SRTMX801-CR',
  'SRTMX802',
  'SRTWB901-BL',
  'SRTWC902',
  'SRTBA903',
  'SRTSK904-GY',
];

export async function mockGetSpecPreview(): Promise<SpecPreviewJobResult> {
  const sample: SpecPreviewSampleRow[] = MOCK_SAMPLE_CODES.map((code, i) => ({
    code,
    before: i % 4 === 0 ? null : 300 + i * 10,
    after: i % 4 === 3 ? null : 300 + i * 10 + (i % 4 === 0 ? 0 : 5),
  }));
  const changed = sample.filter(
    (r) => r.before !== null && r.after !== null && r.before !== r.after,
  ).length;
  const added = sample.filter(
    (r) => r.before === null && r.after !== null,
  ).length;
  const removed = sample.filter(
    (r) => r.before !== null && r.after === null,
  ).length;
  const unchanged = sample.length - changed - added - removed;
  return delay(
    { status: 'done', changed, added, removed, unchanged, sample },
    PREVIEW_DELAY_MS,
  );
}

/**
 * Phase 1 demo seed for the `dim_length` ("Length") key ONLY, in R5's order: the
 * priority a shipped row's kind would run in once S2 ships `shipped_rules()` for it.
 * The real backend has nothing like this today - `dim_length` is read by hard-wired
 * code no screen lists (the plan's Why) - so without this seed AC-C.3 (the shipped tag)
 * has nothing to render against in a browser. Deleted with the rest of this file in S3,
 * when the real GET starts returning these rows with `shipped: true` itself.
 */
export function mockShippedDimLengthRules(): SpecDerivationRule[] {
  const rows: SpecDerivationRule[] = [
    {
      _uid: 'mock-shipped-1',
      builder: { kind: 'from_field', field: 'column:dimensions_length' },
      shipped: true,
      match: 'from_field',
      pattern: 'column:dimensions_length',
    },
    {
      _uid: 'mock-shipped-2',
      builder: { kind: 'size_triple', position: 1 },
      shipped: true,
      match: 'regex',
      pattern: '',
      capture: 1,
    },
    {
      _uid: 'mock-shipped-3',
      builder: { kind: 'number_before', word: 'MM' },
      shipped: true,
      match: 'regex',
      pattern: '',
      capture: 1,
    },
    {
      _uid: 'mock-shipped-4',
      builder: { kind: 'number_after', word: 'L' },
      match: 'regex',
      pattern: '',
      capture: 1,
    },
  ];
  return rows.map((row) => ({
    ...row,
    ...(row.builder ? compileBuilder(row.builder) : {}),
  }));
}
