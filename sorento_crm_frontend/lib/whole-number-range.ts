/**
 * One validator for every operator-typed whole number the media settings surfaces
 * hold to the backend's bounds (system settings and the per-contact overrides).
 * Two copies drifted their copy the first time; one helper keeps the sentence and
 * the rule identical everywhere the same bound is enforced.
 */
export function wholeNumberRangeError(
  raw: string,
  min: number,
  max: number,
  options: { allowBlank?: boolean } = {},
): string | undefined {
  const trimmed = raw.trim();
  if (trimmed === '' && options.allowBlank) return undefined;
  const message = options.allowBlank
    ? `Enter a whole number between ${min} and ${max}, or leave it blank.`
    : `Enter a whole number between ${min} and ${max}.`;
  if (!/^\d+$/.test(trimmed)) return message;
  const value = Number(trimmed);
  return value < min || value > max ? message : undefined;
}
