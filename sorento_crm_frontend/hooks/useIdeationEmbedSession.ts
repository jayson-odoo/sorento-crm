import { useQuery } from '@tanstack/react-query';
import {
  getIdeationEmbedSession,
  type IdeationEmbedSession,
} from '@/services/ideationService';

/**
 * Embed-session hook for the Ideas iframe host (UAC AC-42/44).
 *
 * Calls the real BE mint endpoint via `getIdeationEmbedSession` (Slice D). On failure
 * (shared-service down / dormant settings) the query lands in the error state and
 * `IdeationEmbed` renders its explicit error + Retry CTA - never a blank iframe, never
 * a leaked URL/secret. `retry: false` so the user's manual Retry button drives refetch.
 * The returned `{ iframe_url, token, expires_at }` shape matches the Phase-1 stub, so
 * the board/detail pages are unchanged.
 */
export function useIdeationEmbedSession(ideaId?: string) {
  return useQuery<IdeationEmbedSession, Error>({
    queryKey: ['ideation-embed-session', ideaId ?? 'board'],
    queryFn: () => getIdeationEmbedSession(ideaId),
    // Embed sessions are short-lived; don't serve a stale token across mounts.
    staleTime: 0,
    retry: false,
  });
}
