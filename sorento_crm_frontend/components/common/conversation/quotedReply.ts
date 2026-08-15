import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

/**
 * The quoted text a per-bubble "Reply" carries (UAC AC-L6 / AC-N3).
 *
 * Shared by the ticket drawer and the Conversations inbox: both compose the
 * same ">" prefix through `SharedConversationComposer`, so the excerpt they
 * quote has to be produced the same way or the two surfaces quote the same
 * attachment differently.
 *
 * An attachment has no text, so it is named by its type rather than quoted as
 * an empty line.
 */
export function excerptOfMessage(item: RespondMessageRenderable): string {
  const text = (item.message?.text ?? '').trim();
  if (text) return text;
  const type = String(item.message?.type ?? '').trim();
  return type ? `[${type}]` : '[attachment]';
}
