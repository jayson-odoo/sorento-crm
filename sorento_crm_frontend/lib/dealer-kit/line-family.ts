/**
 * Which tag template family a request line belongs to.
 *
 * Sorento codes are SRT + a family prefix (KS kitchen sink, WB/GB basin,
 * LMCB/MCB mirror cabinet, MR mirror, WT shower set, WC water closet, SP
 * squatting pan, UB urinal, BF bathroom furniture). Matched longest prefix
 * first, so MCB is never read as MR and the SH inside a WC code is never a
 * shower. A set line is always a furniture set. Anything unknown falls back to
 * the ala carte template, which is the plainest layout.
 */

export type LineFamilyInput = { line_type: 'product' | 'product_set' };

const PREFIXES: ReadonlyArray<readonly [string, string]> = [
  ['lmcb', 'mirror_cabinet'],
  ['mcb', 'mirror_cabinet'],
  ['mr', 'mirror'],
  ['ks', 'sink_combo'],
  ['wb', 'art_basin'],
  ['gb', 'art_basin'],
  ['wt', 'shower'],
  ['wc', 'wc'],
  ['sp', 'wc'],
  ['ub', 'urinal'],
  ['bf', 'furniture_set'],
];

export function lineFamily(line: LineFamilyInput, code?: string): string {
  if (line.line_type === 'product_set') return 'furniture_set';
  const body = (code ?? '').toLowerCase().replace(/^srt/, '');
  for (const [prefix, family] of PREFIXES) {
    if (body.startsWith(prefix)) return family;
  }
  return 'ala_carte';
}
