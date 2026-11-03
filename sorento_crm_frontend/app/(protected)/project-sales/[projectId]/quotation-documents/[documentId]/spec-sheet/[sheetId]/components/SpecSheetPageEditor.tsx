'use client';

import * as React from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ensureFontsLoaded } from '@/lib/dealer-kit/fonts';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

import {
  useSpecSheetDetail,
  useSpecSheetMutations,
  useSpecSheetPageDesign,
} from '../../../../../../_shared/hooks/useSpecSheet';
import { COVER, ResetPageButton } from './ReaderPage';

const TagCanvasEditor = dynamic(
  () =>
    import('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor').then((m) => ({
      default: m.TagCanvasEditor,
    })),
  { ssr: false, loading: () => <Skeleton className="h-[400px] w-full" /> },
);

/**
 * Edit one page of a spec sheet in the tag designer: the page's layers (its own override, else the
 * frozen template version's) bound to that page's data. Save page stores them as an override on THIS
 * spec sheet only; the template, its versions and other spec sheets do not change.
 */
export function SpecSheetPageEditor({
  projectId,
  documentId,
  sheetId,
  pageKey,
}: {
  projectId: string;
  documentId: string;
  sheetId: string;
  pageKey: string;
}) {
  const router = useRouter();
  const design = useSpecSheetPageDesign(projectId, documentId, sheetId, pageKey);
  const detail = useSpecSheetDetail(projectId, documentId, sheetId);
  const { savePageEdit } = useSpecSheetMutations(projectId, documentId);
  const layers = React.useRef<TagLayer[] | null>(null);

  const back = `/project-sales/${projectId}/quotation-documents/${documentId}/spec-sheet/${sheetId}`;
  const data = design.data;

  React.useEffect(() => {
    if (data?.fonts?.length) void ensureFontsLoaded(data.fonts);
  }, [data?.fonts]);

  const doc = React.useMemo(
    () => (data ? { layers: data.layers, width_mm: data.width_mm, height_mm: data.height_mm } : null),
    [data],
  );
  const bound = React.useMemo(
    () => (data ? ({ kind: 'line', line: data.bound } as const) : null),
    [data],
  );

  if (design.isLoading) return <Skeleton className="h-[480px] w-full" />;
  if (design.error || !data || !doc) {
    return (
      <div className="rounded-lg border border-border px-4 py-10 text-center">
        <h3 className="text-sm font-semibold text-foreground">The page could not open</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {design.error instanceof Error ? design.error.message : 'Try again in a moment.'}
        </p>
      </div>
    );
  }

  const page = detail.data?.pages.find((p) => p.key === pageKey);
  const isCover = pageKey === COVER;
  const heading = isCover
    ? 'Edit cover'
    : `Edit page ${page?.number ?? ''} · ${page?.code ?? ''}`.replace(/\s+/g, ' ').trim();
  const sub = [detail.data?.label, detail.data?.source_label, data.template_name && `from template ${data.template_name}`]
    .filter(Boolean)
    .join(' · ');

  const save = () =>
    savePageEdit.mutate(
      { sheetId, key: pageKey, layers: layers.current ?? data.layers },
      { onSuccess: () => router.push(back) },
    );

  return (
    <div className="flex min-w-0 flex-col gap-3" data-testid="spec-sheet-page-editor">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-background px-4 py-3">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold">{heading}</h1>
          <div className="truncate text-xs text-muted-foreground" title={sub}>
            {sub}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data.template_id && (
            <Button size="sm" variant="outline" asChild>
              <Link href={`/dealer-kit/tag-templates/${data.template_id}`}>Open template</Link>
            </Button>
          )}
          <Button size="sm" variant="outline" asChild>
            <Link href={back}>Cancel</Link>
          </Button>
          <Button size="sm" disabled={savePageEdit.isPending} onClick={save}>
            Save page
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted px-4 py-2 text-sm">
        <span>
          Changes apply to {isCover ? 'the cover' : `page ${page?.number ?? ''}`.trim()} of{' '}
          {detail.data?.label ?? 'this spec sheet'} only. The template and other spec sheets stay as
          they are.
        </span>
        {data.edited && (
          <ResetPageButton
            documentId={documentId}
            sheetId={sheetId}
            pageKey={pageKey}
            code={isCover ? 'Cover' : (page?.code ?? '')}
            onReset={() => router.push(back)}
          />
        )}
      </div>
      <div className="flex h-[calc(100vh-18rem)] min-h-[32rem] flex-col overflow-hidden rounded-lg border border-border">
        <div className="min-h-0 flex-1">
          <TagCanvasEditor
            key={pageKey}
            doc={doc}
            onChange={(next) => {
              layers.current = next.layers;
            }}
            onLayersChange={(next) => {
              layers.current = next;
            }}
            boundData={bound}
            hideSaveBar
            specSheet
            docId={`${sheetId}:${pageKey}`}
          />
        </div>
      </div>
    </div>
  );
}
