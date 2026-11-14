/**
 * The name a file shows as (its visible, renameable name) and, when the user renamed it, the
 * name it was first uploaded under. A change of letter case alone is not a second name.
 */
export function attachmentDisplayNames(att: {
  stored_filename?: string | null;
  original_filename?: string | null;
}): { name: string; originalName: string | null } {
  const original = (att.original_filename || '').trim();
  const name = (att.stored_filename || '').trim() || original;
  const originalName = original && original.toLowerCase() !== name.toLowerCase() ? original : null;
  return { name, originalName };
}
