'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import {
  AlertCircle,
  Box,
  ClipboardCheck,
  CloudUpload,
  ExternalLink,
  FileDown,
  History,
  Save,
} from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  getPage,
  moveLabel,
  requestExport,
  saveVersion,
} from '../../../services/dealerKitService';
import { PageEditor } from '../../../components/PageEditor';
import { PagePromotionControl } from './PagePromotionControl';
import { PageTileDesignControl } from './PageTileDesignControl';
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
  const [exporting, setExporting] = useState(false);
  /*
    Held here rather than read straight off `page` because the page DETAIL query
    is deliberately never invalidated (refetching it would discard an unsaved
    layout), so after applying a design the query still reports the old one. The
    canvas repaints off THIS, which the control updates the moment the backend
    confirms.
  */
  const [tileTemplateId, setTileTemplateId] = useState<string | null>(null);

  useEffect(() => {
    if (page) {
      setDoc(page.doc);
      setVersions(page.versions);
      setTileTemplateId(page.tileTemplateId);
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
              <Badge variant="success" className="font-normal">
                Live · v{publishedVersion.version}
              </Badge>
            ) : (
              <Badge variant="outline" className="font-normal">
                Not published
              </Badge>
            )}
            {dirty && (
              <Badge variant="warning" className="font-normal">
                Unsaved changes
              </Badge>
            )}
            {/* Saved on its own, not with the document: which promotion prices
                the brochure is a property of the page, so it survives every
                version and does not wait for a publish. */}
            <PagePromotionControl
              pageId={pageId}
              promotionId={page.promotionId}
              promotionLabel={page.promotionLabel}
            />
            {/* Same reasoning, same row: how the tiles look is a property of
                the page, saved on its own, and it takes effect on every
                collection block that does not override it. */}
            <PageTileDesignControl
              pageId={pageId}
              tileTemplateId={tileTemplateId}
              tileTemplateName={page.tileTemplateName}
              onApplied={(link) => setTileTemplateId(link.tileTemplateId)}
            />
          </div>

          {/* Two buttons and a gear. This row carried SIX actions - export,
              view live, design a room, history, save, publish - all competing
              at the same weight, and the two that change the catalogue were
              the hardest to find among them. Everything that is not "save what
              I typed" or "put it in front of readers" now lives under the gear,
              which is the pattern the rest of the system already uses
              (DetailActionsMenu: complaints, purchase requests, stock
              inquiries). */}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleSave} disabled={!dirty || saving}>
              <Save className="size-4" />
              {saving ? 'Saving' : 'Save page'}
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
            <DetailActionsMenu ariaLabel="Catalogue actions">
              {/* The only way into the approval workflow. It lives here rather
                  than as a header button because most visits to this screen are
                  ordinary editing, and starting a revision cycle is a decision
                  somebody makes once per season. */}
              <DropdownMenuItem asChild>
                <Link href={`/dealer-kit/editions?pageId=${pageId}`}>
                  <ClipboardCheck className="size-4" />
                  Editions and approval
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setShowHistory((open) => !open)}>
                <History className="size-4" />
                {showHistory ? 'Hide version history' : 'Version history'}
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                {/* The journey is catalogue -> room. Before this link existed
                    you had to go back to the sidebar and start the designer
                    cold, having just chosen the products. */}
                <Link href={`/dealer-kit/design?from=${pageId}`}>
                  <Box className="size-4" />
                  Design a room
                </Link>
              </DropdownMenuItem>
              {/* Both of these need something LIVE. Exporting a draft nobody
                  published produces a file that disagrees with the catalogue,
                  and a link to an unpublished page 404s and reads as a broken
                  feature. Hidden rather than disabled: an item that can never
                  be used on a draft is noise on a draft. */}
              {publishedVersion && (
                <DropdownMenuItem
                  disabled={exporting}
                  onSelect={async (event) => {
                    // The menu would close under the await and the toast would
                    // arrive with nothing on screen to attach it to.
                    event.preventDefault();
                    setExporting(true);
                    try {
                      await requestExport(pageId, 'staff');
                      toast.success('Building your PDF. It will appear in My Downloads.');
                    } catch (error) {
                      toast.error(
                        error instanceof Error ? error.message : 'Could not start the export.',
                      );
                    } finally {
                      setExporting(false);
                    }
                  }}
                >
                  <FileDown className="size-4" />
                  {exporting ? 'Starting export' : 'Export PDF'}
                </DropdownMenuItem>
              )}
              {publishedVersion && page.publicPath && (
                <DropdownMenuItem asChild>
                  <a href={page.publicPath} target="_blank" rel="noreferrer">
                    <ExternalLink className="size-4" />
                    View live
                  </a>
                </DropdownMenuItem>
              )}
            </DetailActionsMenu>
          </div>
        </CardContent>
      </Card>

      {showHistory && (
        <VersionHistory versions={versions} onPublish={handlePublish} />
      )}

      <PageEditor
        pageId={pageId}
        doc={doc}
        /*
          Straight from the page payload, the same map the public catalogue and
          the print route receive. Read off `page` rather than mirrored into
          state: the working document changes as the designer edits, but the
          signed URLs belong to the load, and copying them would be a second
          copy to keep in step for no gain.
        */
        assets={page.assets}
        defaultTileTemplateId={tileTemplateId}
        onDocChange={(updater, options) => {
          setDoc((previous) => (previous ? updater(previous) : previous));
          if (!options?.silent) setDirty(true);
        }}
      />
    </div>
  );
}
