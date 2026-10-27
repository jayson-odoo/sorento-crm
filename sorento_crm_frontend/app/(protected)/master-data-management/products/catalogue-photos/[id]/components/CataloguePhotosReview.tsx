'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Download, FolderOpen, LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { WizardSteps } from '@/components/common/WizardSteps';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useHasPermission } from '@/hooks/usePermissions';
import AttachmentBulkDownloadDialog from '@/app/(protected)/resource-management/attachments/components/AttachmentBulkDownloadDialog';
import {
  useCatalogPhotoMutations,
  useCatalogPhotoReadingQuery,
} from '../../../hooks/useCatalogPhotoReadings';
import type { CatalogPhotoTab } from '../../../services/catalogPhotoReadingService';
import { CataloguePhotosGrid } from './CataloguePhotosGrid';

const STEPS = [
  { id: 'upload', label: 'Upload' },
  { id: 'review', label: 'Review' },
  { id: 'attach', label: 'Attach' },
] as const;

export function CataloguePhotosReview({ id }: { id: string }) {
  const reading = useCatalogPhotoReadingQuery(id);
  const { attach } = useCatalogPhotoMutations(id);
  const canAttach = useHasPermission('master_data.products.edit');
  const [tab, setTab] = useState<CatalogPhotoTab>('ready');
  const [zipOpen, setZipOpen] = useState(false);
  const [attached, setAttached] = useState(false);

  const data = reading.data;
  if (reading.isError) {
    return (
      <Container width="fluid">
        <PageHeader title="Catalogue photos" />
        <Alert variant="destructive">
          <AlertDescription>
            {reading.error instanceof Error ? reading.error.message : 'Could not load this catalogue'}
          </AlertDescription>
        </Alert>
      </Container>
    );
  }
  if (!data) {
    return (
      <Container width="fluid">
        <PageHeader title={<Skeleton className="h-7 w-72" />} crumbTitle="Catalogue photos" />
        <Skeleton className="h-64 w-full" />
      </Container>
    );
  }

  const inProgress = data.status === 'queued' || data.status === 'reading';
  const ready = data.status === 'ready';
  const toAttach = data.counts.to_attach;
  const step = attached ? 'attach' : ready ? 'review' : 'upload';
  const counts = data.counts;

  const tabs: { value: CatalogPhotoTab; label: string; count: number }[] = [
    { value: 'ready', label: 'Ready', count: counts.ready },
    { value: 'duplicate', label: 'Looks like an existing photo', count: counts.duplicate },
    { value: 'needs_product', label: 'Needs a product', count: counts.needs_product },
    { value: 'skipped', label: 'Skipped', count: counts.skipped },
  ];

  return (
    <Container width="fluid">
      <PageHeader
        title={data.file_name}
        titleClassName="break-all"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {data.directory_id ? (
              <Button variant="outline" asChild>
                <Link href={`/resource-management/attachment-directories?directoryId=${data.directory_id}`}>
                  <FolderOpen className="size-4" />
                  Open folder
                </Link>
              </Button>
            ) : null}
            <Button variant="outline" disabled={!ready} onClick={() => setZipOpen(true)}>
              <Download className="size-4" />
              Download all as ZIP
            </Button>
            <Button
              disabled={!ready || !canAttach || toAttach === 0 || attach.isPending}
              onClick={() =>
                attach.mutate(undefined, { onSuccess: () => setAttached(true) })
              }
            >
              {attach.isPending
                ? 'Attaching'
                : `Attach ${toAttach} ${toAttach === 1 ? 'photo' : 'photos'}`}
            </Button>
          </div>
        }
      />

      <dl className="mb-4 flex flex-wrap gap-x-6 gap-y-1 border-b border-border pb-3 text-sm text-muted-foreground">
        <div className="flex gap-1">
          <dd className="font-medium text-foreground tabular-nums">{data.page_count ?? '-'}</dd>
          <dt>pages</dt>
        </div>
        <div className="flex gap-1">
          <dd className="font-medium text-foreground tabular-nums">{data.photo_count ?? '-'}</dd>
          <dt>photos</dt>
        </div>
        <div className="flex gap-1">
          <dt>Read</dt>
          <dd className="font-medium text-foreground">{formatDateTimeInMalaysia(data.created_at)}</dd>
        </div>
        <div className="flex gap-1">
          <dt>By</dt>
          <dd className="font-medium text-foreground">{data.created_by_name ?? '-'}</dd>
        </div>
      </dl>

      <WizardSteps steps={STEPS} currentId={step} className="mb-4 max-w-md" />

      {data.status === 'failed' ? (
        <Alert variant="destructive">
          <AlertDescription>{data.error ?? 'This catalogue could not be read'}</AlertDescription>
        </Alert>
      ) : inProgress ? (
        <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground" role="status">
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
          {data.status === 'queued' ? 'Waiting to start' : 'Reading the catalogue'}
        </div>
      ) : (
        <>
          <Tabs value={tab} onValueChange={(next) => setTab(next as CatalogPhotoTab)}>
            <TabsList variant="line" className="mb-4 w-full">
              {tabs.map((item) => (
                <TabsTrigger key={item.value} value={item.value}>
                  {item.label} ({item.count})
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <CataloguePhotosGrid key={tab} readingId={id} tab={tab} locked={attach.isPending} />
        </>
      )}

      <AttachmentBulkDownloadDialog
        open={zipOpen}
        onOpenChange={setZipOpen}
        directoryId={data.directory_id}
        folderIds={[]}
        attachmentIds={[]}
      />
    </Container>
  );
}
