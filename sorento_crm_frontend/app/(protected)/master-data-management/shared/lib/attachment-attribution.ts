/**
 * Uploader attribution label shared by every CRM "Linked Attachments" panel
 * (complaint / stock inquiry / purchase request-sponsorship form). Renders
 * "by <name> (contact)" / "by <name> (staff)"; an unresolved uploader renders
 * the explicit "Unknown" rather than a guessed name or a raw UUID.
 * See docs/plans/UAC-response-attachments.md group B.
 */
export type AttachmentUploaderRole = 'contact' | 'staff' | null | undefined;

export function attachmentUploaderLabel(
  name: string | null | undefined,
  role: AttachmentUploaderRole,
): string {
  const trimmed = name?.trim();
  if (!trimmed) return 'Unknown';
  if (role === 'contact') return `by ${trimmed} (contact)`;
  if (role === 'staff') return `by ${trimmed} (staff)`;
  return trimmed;
}
