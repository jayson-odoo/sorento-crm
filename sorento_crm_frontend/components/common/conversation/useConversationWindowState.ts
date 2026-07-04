'use client';

import { useQuery, type QueryClient } from '@tanstack/react-query';
import { getWindowState, type WindowState } from '@/services/whatsappTemplateService';

/**
 * Refetch the 24h window-state AND the chat-template preview for a conversation.
 * Call this from a panel's "refresh" control so re-checking messages also
 * re-evaluates open/closed (an incoming reply re-opens the window → the composer
 * flips from template mode back to the plain textbox). Single source of the keys
 * so they can't drift from `useConversationWindowState` / the composer.
 */
export function invalidateConversationWindow(
  queryClient: QueryClient,
  entityType: string,
  entityId: string,
): void {
  queryClient.invalidateQueries({ queryKey: ['whatsapp-window-state', entityType, entityId] });
  queryClient.invalidateQueries({ queryKey: ['chat-template-preview', entityType, entityId] });
}

/**
 * 24h WhatsApp window state for a conversation surface. Display-only — used to
 * render the out-of-window hint. The actual plain-vs-template send decision is
 * made server-side at send time (no client gating), so this never blocks sends.
 */
export function useConversationWindowState(
  entityType: string,
  entityId: string,
  enabled: boolean,
): { windowState: WindowState | undefined; windowClosed: boolean } {
  const { data: windowState } = useQuery({
    queryKey: ['whatsapp-window-state', entityType, entityId],
    queryFn: () => getWindowState(entityType, entityId),
    enabled,
    staleTime: 60_000,
  });
  return { windowState, windowClosed: windowState ? !windowState.open : false };
}
