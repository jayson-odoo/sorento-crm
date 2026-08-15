/**
 * Document number rendering for revisable portal submissions (UAC N).
 *
 * The stored number NEVER changes: `inquiry_number` stays `SI-26-0184` and the
 * `-R2` suffix is DERIVED from the denormalized `revision_no` at render time.
 * Every lookup-by-number, index, import and integration therefore keeps working
 * against the bare value, while every screen shows which revision it is looking
 * at (N1/N2).
 *
 * `revision_no = 0` renders bare - there is no `-R0` (N3).
 *
 * Use this helper everywhere the number appears (list, detail, banner) so the
 * suffix can never show on one surface and not another (N4).
 */

/** `SI-26-0184` + revision 2 -> `SI-26-0184-R2`. Revision 0 (or unknown) renders bare. */
export function withRevisionSuffix(
  documentNumber: string | null | undefined,
  revisionNo: number | null | undefined,
): string | null {
  const base = (documentNumber ?? '').trim();
  if (!base) return null;
  const rev = Number(revisionNo ?? 0);
  if (!Number.isFinite(rev) || rev <= 0) return base;
  return `${base}-R${Math.trunc(rev)}`;
}

/** Short badge text for a list column: `Rev 2`, or null at revision 0. */
export function revisionBadgeLabel(revisionNo: number | null | undefined): string | null {
  const rev = Number(revisionNo ?? 0);
  if (!Number.isFinite(rev) || rev <= 0) return null;
  return `Rev ${Math.trunc(rev)}`;
}

/** Strip a trailing `-R<n>` so a pasted/echoed number still matches the stored one (N6/N7). */
export function stripRevisionSuffix(value: string | null | undefined): string | null {
  const raw = (value ?? '').trim();
  if (!raw) return null;
  return raw.replace(/-R\d+$/i, '');
}
