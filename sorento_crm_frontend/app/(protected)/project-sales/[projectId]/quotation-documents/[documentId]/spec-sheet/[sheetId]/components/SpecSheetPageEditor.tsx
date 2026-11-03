'use client';

import * as React from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import DetailActions from '@/components/common/DetailActions';
import { ensureFontsLoaded } from '@/lib/dealer-kit/fonts';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

import {
  useSpecSheetDetail,
  useSpecSheetMutations,
  useSpecSheetPageDesign,
} from '../../../../../../_shared/hooks/useSpecSheet';
import { COVER, ResetPageButton } from './ReaderPage';
import { projectCrumbs } from '../../../../../../_shared/lib/crumbs';

const TagCanvasEditor = dynamic(
  () =>
    import('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor').then(
      (m) => ({
        default: m.TagCanvasEditor,
      }),
    ),
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
  const design = useSpecSheetPageDesign(
    projectId,
    documentId,
    sheetId,
    pageKey,
  );
  const detail = useSpecSheetDetail(projectId, documentId, sheetId);
  const { savePageEdit } = useSpecSheetMutations(projectId, documentId);
  const layers = React.useRef<TagLayer[] | null>(null);

  const listHref = `/project-sales/${projectId}/quotation-documents/${documentId}/spec-sheet`;
  const back = `${listHref}/${sheetId}`;
  const data = design.data;

  React.useEffect(() => {
    if (data?.fonts?.length) void ensureFontsLoaded(data.fonts);
  }, [data?.fonts]);

  const doc = React.useMemo(
    () =>
      data
        ? {
            layers: data.layers,
            width_mm: data.width_mm,
            height_mm: data.height_mm,
          }
        : null,
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
        <h3 className="text-sm font-semibold text-foreground">
          The page could not open
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {design.error instanceof Error
            ? design.error.message
            : 'Try again in a moment.'}
        </p>
      </div>
    );
  }

  const page = detail.data?.pages.find((p) => p.key === pageKey);
  const isCover = pageKey === COVER;
  const heading = isCover
    ? 'Edit cover'
    : `Edit page ${page?.number ?? ''} · ${page?.code ?? ''}`
        .replace(/\s+/g, ' ')
        .trim();
  const save = () =>
    savePageEdit.mutate(
      { sheetId, key: pageKey, layers: layers.current ?? data.layers },
      { onSuccess: () => router.push(back) },
    );

  return (
    <div
      className="flex min-w-0 flex-col gap-3"
      data-testid="spec-sheet-page-editor"
    >
      <PageHeader
        title={heading}
        crumbs={projectCrumbs(
          projectId,
          { tab: 'quotations' },
          { title: 'Spec sheets', path: listHref },
          { title: detail.data?.label ?? 'Spec sheet', path: back },
          { title: heading },
        )}
        titleClassName="truncate"
        actions={
          <BackToList
            listPath={back}
            label="Back to spec sheet"
            appendListState={false}
          />
        }
      />
      {/* The system's detail-page group: gear for the secondary, then the one primary. */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        {data.edited && (
          <ResetPageButton
            documentId={documentId}
            sheetId={sheetId}
            pageKey={pageKey}
            code={isCover ? 'Cover' : (page?.code ?? '')}
            onReset={() => router.push(back)}
          />
        )}
        <DetailActions
          actions={
            data.template_id
              ? [
                  {
                    key: 'spec_sheet_page.open_template',
                    label: 'Open template',
                    run: () =>
                      router.push(
                        `/dealer-kit/tag-templates/${data.template_id}`,
                      ),
                  },
                ]
              : []
          }
          gearLabel="Page actions"
          primary={
            <Button size="sm" disabled={savePageEdit.isPending} onClick={save}>
              Save page
            </Button>
          }
        />
      </div>
      <div className="flex h-[calc(100dvh-18rem)] min-h-[32rem] flex-col overflow-hidden rounded-lg border border-border">
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
            // The page's medium renditions: the editor must not resolve library artwork to its
            // original, which can be megabytes.
            assetUrls={data.assets}
            hideSaveBar
            specSheet
            docId={`${sheetId}:${pageKey}`}
          />
        </div>
      </div>
    </div>
  );
}
