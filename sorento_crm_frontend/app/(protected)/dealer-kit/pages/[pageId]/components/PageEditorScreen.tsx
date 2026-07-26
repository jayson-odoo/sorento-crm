'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, CloudUpload, ExternalLink, History, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { getPage, moveLabel, saveVersion } from '../../../services/dealerKitService';
import { PageEditor } from '../../../components/PageEditor';
import { VersionHistory } from './VersionHistory';
import type { PageDoc, PageVersion } from '@/lib/dealer-kit/types';

/**
 * Editor screen. Owns the working document, which is deliberately NOT the saved
 * version: Preview renders this buffer, so what a Designer sees is what they are
 * about to save. The prompt-registry dry-run trap - previewing the SAVED version
 * while the editor shows an unsaved one - is the thing being avoided here (AC-B9).
 */
export function PageEditorScreen({ pageId }: { pageId: string }) {
  const { data: page, isLoading, isError, error } = useQuery({
    queryKey: ['dealer-kit', 'page', pageId],
    queryFn: () => getPage(pageId),
    retry: false,
  });

  const [doc, setDoc] = useState<PageDoc | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [versions, setVersions] = useState<PageVersion[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (page) {
      setDoc(page.doc);
      setVersions(page.versions);
      setDirty(false);
    }
  }, [page]);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 lg:flex-row">
        <Skeleton className="h-96 w-full lg:w-56" />
        <Skeleton className="h-96 min-w-0 flex-1" />
      </div>
    );
  }

  if (isError || !page || !doc) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not open this page</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : 'This page does not exist, or you cannot see it.'}
        </AlertDescription>
      </Alert>
    );
  }

  const publishedVersion = versions.find((version) => version.labels.includes('published'));
  const latest = versions[0];

  const handleSave = async () => {
    setSaving(true);
    try {
      const created = await saveVersion(pageId, doc, '');
      setVersions((current) => [created, ...current]);
      setDirty(false);
      toast.success(`Saved as version ${created.version}`);
    } catch (saveError) {
      toast.error(
        saveError instanceof Error ? saveError.message : 'Could not save. Try again.',
      );
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async (versionId: string) => {
    try {
      await moveLabel(pageId, 'published', versionId);
      // Recompute locally rather than refetching: the label is a pointer, so
      // exactly one version can hold it and the new state is fully determined.
      setVersions((current) =>
        current.map((version) => ({
          ...version,
          labels: version.id === versionId
            ? Array.from(new Set([...version.labels, 'published' as const]))
            : version.labels.filter((label) => label !== 'published'),
        })),
      );
      const target = versions.find((version) => version.id === versionId);
      toast.success(`Version ${target?.version} is now live`);
    } catch (publishError) {
      toast.error(
        publishError instanceof Error ? publishError.message : 'Could not publish. Try again.',
      );
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="truncate font-medium">{page.name}</span>
            {publishedVersion ? (
              <Badge variant="success" appearance="ghost" className="font-normal">
                Live · v{publishedVersion.version}
              </Badge>
            ) : (
              <Badge variant="outline" appearance="ghost" className="font-normal">
                Not published
              </Badge>
            )}
            {dirty && (
              <Badge variant="warning" appearance="ghost" className="font-normal">
                Unsaved changes
              </Badge>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {publishedVersion && page.publicPath && (
              // Only once something is live: a link to a page that 404s reads
              // as a broken feature rather than an unpublished draft.
              <Button variant="outline" size="sm" asChild>
                <a href={page.publicPath} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-4" />
                  View live
                </a>
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => setShowHistory((open) => !open)}>
              <History className="size-4" />
              History
            </Button>
            <Button variant="outline" size="sm" onClick={handleSave} disabled={!dirty || saving}>
              <Save className="size-4" />
              {saving ? 'Saving' : 'Save'}
            </Button>
            <Button
              size="sm"
              disabled={!latest || dirty}
              onClick={() => latest && handlePublish(latest.id)}
              title={dirty ? 'Save before publishing' : undefined}
            >
              <CloudUpload className="size-4" />
              Publish
            </Button>
          </div>
        </CardContent>
      </Card>

      {showHistory && (
        <VersionHistory versions={versions} onPublish={handlePublish} />
      )}

      <PageEditor
        doc={doc}
        onDocChange={(updater, options) => {
          setDoc((previous) => (previous ? updater(previous) : previous));
          if (!options?.silent) setDirty(true);
        }}
      />
    </div>
  );
}
