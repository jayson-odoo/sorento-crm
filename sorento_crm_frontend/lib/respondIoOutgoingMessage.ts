/**
 * Respond.io conversation API: map outgoing message sender.source to UI label + bubble style.
 */

export function getNormalizedRespondSource(item: {
  sender?: { source?: string | null };
}): string {
  return (item.sender?.source ?? '').trim().toLowerCase();
}

/** The colleague who sent this message, resolved by the backend from `sender.userId`. */
export function getRespondSenderName(item: {
  sender?: { name?: string | null };
}): string {
  return (item.sender?.name ?? '').trim();
}

/**
 * Label above an outgoing bubble, or null for no label at all.
 *
 * A machine send gets NO label. The thread is our side of one conversation, so
 * naming the transport that carried a message ("n8n") tells the reader nothing
 * they can act on and leaks an internal tool name into a customer-facing
 * surface. A colleague's own send is the case where the name matters - "who
 * replied to this customer" is a real question - so those keep their name, and
 * an unresolvable one falls back to no label rather than to a placeholder.
 */
export function getOutgoingSenderLabel(
  sourceNorm: string,
  senderName?: string | null,
): string | null {
  if (sourceNorm !== 'user') return null;
  const name = (senderName ?? '').trim();
  return name || null;
}

/** Tailwind classes for outgoing bubble background/text (incoming uses bg-muted elsewhere). */
export function getOutgoingBubbleClass(sourceNorm: string): string {
  if (sourceNorm === 'n8n') return 'bg-amber-800 text-white';
  if (sourceNorm === 'workflow') return 'bg-violet-600 text-white';
  if (sourceNorm === 'ai_agent' || sourceNorm === 'agent') return 'bg-violet-500/90 text-white';
  return 'bg-primary text-primary-foreground';
}
