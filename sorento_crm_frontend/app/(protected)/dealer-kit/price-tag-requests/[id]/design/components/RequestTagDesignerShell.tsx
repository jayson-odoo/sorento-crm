'use client';

/**
 * Shell that loads the request and its tag sheet document, then renders the
 * designer.
 *
 * Separated so that the page.tsx stays a server component for metadata, and so
 * the whole Konva tree below it is loaded with ssr:false in one place.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from '@/lib/toast';
import type {
  TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import {
  getPriceTagRequest,
  getTagSheetDoc,
  saveTagSheetDoc,
  saveTagSheetDraft,
  type PriceTagRequestDetail,
} from '../../../../services/priceTagRequestService';
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';

const RequestTagDesigner = dynamic(
  () =>
    import('./RequestTagDesigner').then((m) => ({ default: m.RequestTagDesigner })),
  { ssr: false, loading: () => <Skeleton className="h-[400px] w-full" /> },
);

interface Props {
  requestId: string;
}

export default function RequestTagDesignerShell({ requestId }: Props) {
  const [request, setRequest] = useState<PriceTagRequestDetail | null>(null);
  const [initialDoc, setInitialDoc] = useState<TagSheetDoc | null | undefined>(
    undefined,
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      getPriceTagRequest(requestId),
      getTagSheetDoc(requestId),
    ])
      .then(([req, doc]) => {
        if (cancelled) return;
        setRequest(req);
        setInitialDoc(doc);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [requestId]);

  /**
   * Autosave: silent, and it RETHROWS (B2/B3).
   *
   * Two different acts were sharing one handler, and the autosave inherited
   * the manual button's manners: a "Tag sheet saved" toast roughly once a
   * second while the designer worked (D22 asks for an indicator, not a
   * announcement), and - worse - a swallowed failure, which left the header
   * saying "Saved" when nothing had been. The indicator is the whole report
   * for this path, and it can only say "Save failed" if the rejection reaches
   * `useAutosave`.
   *
   * It writes the DRAFT, never a version (B1): sixty autosaves are one row
   * overwritten sixty times, not sixty entries in the request's history.
   */
  const handleAutosave = useCallback(
    async (doc: TagSheetDoc, options: { keepalive?: boolean } = {}) => {
      await saveTagSheetDraft(requestId, doc, options);
    },
    [requestId],
  );

  /**
   * Manual Save: the deliberate act, so it keeps its toast - and rethrows so a
   * caller that saves as a PRECONDITION (Mark proof ready, Print sheet) can
   * abort instead of transitioning a request whose design never landed.
   */
  const handleSave = useCallback(
    async (doc: TagSheetDoc) => {
      try {
        await saveTagSheetDoc(requestId, doc);
        toast.success('Tag sheet saved');
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to save tag sheet');
        throw err;
      }
    },
    [requestId],
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">
          Loading designer...
        </span>
      </div>
    );
  }

  if (!request) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Request not found.</p>
      </div>
    );
  }

  return (
    <RequestTagDesigner
      request={request}
      initialDoc={initialDoc ?? null}
      onSave={handleSave}
      onAutosave={handleAutosave}
    />
  );
}
