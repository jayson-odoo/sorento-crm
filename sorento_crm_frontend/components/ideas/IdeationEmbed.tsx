'use client';

import { AlertCircle } from 'lucide-react';
import { ContentLoader } from '@/components/common/content-loader';
import { Button } from '@/components/ui/button';
import { useIdeationEmbedSession } from '@/hooks/useIdeationEmbedSession';

interface IdeationEmbedProps {
  /** Opaque idea id for the detail view; omit for the board. Never rendered as visible text (AC-41). */
  ideaId?: string;
  /** Accessible title for the iframe. */
  title: string;
}

/**
 * Hosts the shared-service ideation UI inside an <iframe>, authenticated via a
 * short-lived embed session (Phase 1: stubbed hook). Covers loading / error+retry
 * states (UAC AC-44); never renders a blank iframe, a raw URL, or the token as text.
 */
export function IdeationEmbed({ ideaId, title }: IdeationEmbedProps) {
  const { data, isPending, isError, refetch, isFetching } =
    useIdeationEmbedSession(ideaId);

  if (isPending) {
    return (
      <div className="flex min-h-[70vh] flex-col">
        <ContentLoader />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center gap-4 text-center">
        <AlertCircle className="size-10 text-destructive" />
        <div className="space-y-1">
          <p className="text-base font-semibold text-mono">
            Couldn&apos;t open the Ideas workspace
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            We couldn&apos;t start a secure session. Please try again in a moment.
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? 'Retrying…' : 'Retry'}
        </Button>
      </div>
    );
  }

  // Token travels to the iframe in the URL FRAGMENT (not a query param) so it stays
  // out of server logs and the Referer header (AC-E-10) — never shown to the user.
  const src = `${data.iframe_url}#token=${encodeURIComponent(data.token)}`;

  return (
    <iframe
      title={title}
      src={src}
      className="h-[calc(100vh-8rem)] min-h-[70vh] w-full rounded-lg border border-border bg-background"
      // Sandboxed embed of a trusted first-party shared-service origin.
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
    />
  );
}
