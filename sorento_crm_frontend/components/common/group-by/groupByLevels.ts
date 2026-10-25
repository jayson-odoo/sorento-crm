import { fromMinor, toMinor } from '@/app/(protected)/project-sales/_shared/lib/supplyComposition';

export type Measure<T> = (line: T) => string | number | null | undefined;

export interface GroupDimension<T> {
  id: string;
  label: string;
  noneLabel: string;
  /** Trimmed by the engine; '' / whitespace / null / undefined all mean "none". */
  valueOf: (line: T) => string | null | undefined;
  /** Fixed order when given (lower first, ties and unranked values A to Z); else A to Z. */
  rank?: (value: string) => number;
}

export interface GroupNode<T> {
  /** Path of `dimension=value` pieces; the none group has an empty value (`project=`). */
  key: string;
  dimension: string;
  label: string;
  isNone: boolean;
  depth: number;
  count: number;
  /** Exact decimal strings per measure id, summed in minor units so 0.1 + 0.2 reads 0.3. */
  sums: Record<string, string>;
  children: GroupNode<T>[];
  /** Every line beneath, in input order. */
  lines: T[];
}

function byName(a: string, b: string): number {
  const x = a.toLowerCase();
  const y = b.toLowerCase();
  return x < y ? -1 : x > y ? 1 : 0;
}

function build<T>(
  lines: readonly T[],
  levels: readonly GroupDimension<T>[],
  measures: Record<string, Measure<T>>,
  depth: number,
  parentKey: string,
): GroupNode<T>[] {
  const [dim, ...rest] = levels;
  if (!dim) return [];
  const buckets = new Map<string, T[]>();
  for (const line of lines) {
    const value = (dim.valueOf(line) ?? '').trim();
    const bucket = buckets.get(value);
    if (bucket) bucket.push(line);
    else buckets.set(value, [line]);
  }
  const values = [...buckets.keys()].sort((a, b) => {
    if (a === '' || b === '') return a === b ? 0 : a === '' ? 1 : -1;
    if (dim.rank) {
      const ra = dim.rank(a);
      const rb = dim.rank(b);
      if (ra !== rb) return ra < rb ? -1 : 1;
    }
    return byName(a, b);
  });
  return values.map((value) => {
    const inGroup = buckets.get(value) as T[];
    const key = `${parentKey}${dim.id}=${value}`;
    const sums: Record<string, string> = {};
    for (const [id, measure] of Object.entries(measures)) {
      sums[id] = fromMinor(inGroup.reduce((total, line) => total + toMinor(measure(line)), 0));
    }
    return {
      key,
      dimension: dim.id,
      label: value === '' ? dim.noneLabel : value,
      isNone: value === '',
      depth,
      count: inGroup.length,
      sums,
      children: build(inGroup, rest, measures, depth + 1, `${key}/`),
      lines: inGroup,
    };
  });
}

/** Splits `lines` level by level into a tree of groups; no levels gives no groups. */
export function groupByLevels<T>(
  lines: readonly T[],
  levels: readonly GroupDimension<T>[],
  measures: Record<string, Measure<T>>,
): GroupNode<T>[] {
  return build(lines, levels, measures, 0, '');
}
