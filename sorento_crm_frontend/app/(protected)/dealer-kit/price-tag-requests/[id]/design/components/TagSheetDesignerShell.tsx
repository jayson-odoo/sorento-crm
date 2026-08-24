'use client';

/**
 * Shell that loads the request and tag sheet doc, then renders the designer.
 *
 * Separated so that the page.tsx stays a server component for metadata.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import type {
  TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import {
  getPriceTagRequest,
  getTagSheetDoc,
  saveTagSheetDoc,
  type PriceTagRequestDetail,
} from '../../../../services/priceTagRequestService';
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';

const TagSheetDesigner = dynamic(
  () => import('./TagSheetDesigner').then((m) => ({ default: m.TagSheetDesigner })),
  { ssr: false, loading: () => <Skeleton className="h-[400px] w-full" /> },
);

interface Props {
  requestId: string;
}

export default function TagSheetDesignerShell({ requestId }: Props) {
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

  const handleSave = useCallback(
    async (doc: TagSheetDoc) => {
      try {
        await saveTagSheetDoc(requestId, doc);
        toast.success('Tag sheet saved');
      } catch {
        toast.error('Failed to save tag sheet');
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
    <TagSheetDesigner
      request={request}
      initialDoc={initialDoc ?? null}
      onSave={handleSave}
    />
  );
}
