/**
 * One line for a system event in an activity feed. Shared by the drawer and the entity layout.
 *
 * Order: the known wording for ticket events; otherwise the sentence the writer saved
 * (`body_text`, e.g. "PRJQ-2026-0009 copied from PRJQ-2026-0003 for ..."); otherwise the
 * template key made readable. A raw key such as `quotation_created` is never shown.
 */
export function formatSystemEvent(
  template: string | null | undefined,
  payload: Record<string, unknown> | null | undefined,
  bodyText?: string | null,
): string {
  const t = template ?? '';
  const p = payload ?? {};
  switch (t) {
    case 'entity.created':
      return `Ticket ${(p.ticket_number as string) ?? ''} was created.`;
    case 'status.changed':
      return `Status changed: ${(p.from as string) ?? '?'} → ${(p.to as string) ?? '?'}${
        p.note ? ` - ${p.note as string}` : ''
      }`;
    case 'assignee.changed':
      return 'Assignee changed.';
    case 'response.updated':
      return p.first_response ? 'First response posted.' : 'Response updated.';
    case 'resolution.updated':
      return 'Resolution updated.';
    case 'watchers.added':
      return 'Watchers added.';
    case 'watchers.removed':
      return 'Watcher removed.';
    case 'message.sent':
      return 'Outbound message sent.';
    default: {
      if (bodyText && bodyText.trim()) return bodyText.trim();
      const readable = t.replace(/[._]+/g, ' ').trim();
      return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : 'System event';
    }
  }
}
