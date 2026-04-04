/**
 * Respond.io conversation API: map outgoing message sender.source to UI label + bubble style.
 */

export function getNormalizedRespondSource(item: {
  sender?: { source?: string | null };
}): string {
  return (item.sender?.source ?? '').trim().toLowerCase();
}

/** Label above outgoing bubble (not shown for incoming). */
export function getOutgoingSenderLabel(sourceNorm: string): string {
  if (sourceNorm === 'n8n') return 'n8n';
  if (sourceNorm === 'workflow') return 'Workflow';
  if (sourceNorm === 'ai_agent' || sourceNorm === 'agent') return 'AI Agent';
  return 'User';
}

/** Tailwind classes for outgoing bubble background/text (incoming uses bg-muted elsewhere). */
export function getOutgoingBubbleClass(sourceNorm: string): string {
  if (sourceNorm === 'n8n') return 'bg-amber-800 text-white';
  if (sourceNorm === 'workflow') return 'bg-violet-600 text-white';
  if (sourceNorm === 'ai_agent' || sourceNorm === 'agent') return 'bg-violet-500/90 text-white';
  return 'bg-primary text-primary-foreground';
}
