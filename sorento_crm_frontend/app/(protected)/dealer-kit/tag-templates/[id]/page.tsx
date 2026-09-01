'use client';

/**
 * Tag template editor page.
 *
 * Loads the template by id and renders the full TagCanvasEditor against its
 * DRAFT doc. Save writes the draft (unchanged). Publish snapshots the draft
 * into an immutable version and moves the live pointer (S5, PLAN D7) - the
 * request designer's template source reads only that pointer's doc, never
 * this draft, so an in-progress edit is never at risk of going live by
 * accident.
 *
 * View, from the Versions sheet, swaps the canvas to a read-only render of
 * that version (D16) via `TagVersionViewer`; the draft in memory is
 * untouched underneath it, so Back to draft returns exactly where editing
 * left off.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { toast } from 'sonner';
import { History, Save as SaveIcon, Upload } from 'lucide-react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import dynamic from 'next/dynamic';
import type {
  TagLayer,
  TagTemplate,
  TagTemplateVersionDetail,
} from '@/lib/dealer-kit/tag-template-types';
import {
  getTemplate,
  getTemplateVersion,
  publishTemplate,
  restoreTemplateVersion,
  updateTemplate,
} from '../../services/tagTemplateService';
import { TemplateVersionsSheet } from '../components/TemplateVersionsSheet';

const TagCanvasEditor = dynamic(
  () => import('../components/TagCanvasEditor').then((m) => ({ default: m.TagCanvasEditor })),
  { ssr: false, loading: () => <Skeleton className="h-[400px] w-full" /> },
);
const TagVersionViewer = dynamic(
  () => import('../components/TagVersionViewer').then((m) => ({ default: m.TagVersionViewer })),
  { ssr: false, loading: () => <Skeleton className="h-[400px] w-full" /> },
);

export default function TagTemplateEditorPage() {
  const params = useParams<{ id: string }>();

  const [template, setTemplate] = useState<TagTemplate | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The header owns Save (AC-S5-5, the bottom save bar is gone), so the
  // current layers have to reach it from inside the canvas. `onLayersChange`
  // streams every edit up here - the same mechanism the request designer
  // uses for the same reason (switching what the canvas points at must not
  // throw work away).
  const [draftLayers, setDraftLayers] = useState<TagLayer[]>([]);
  const [saving, setSaving] = useState(false);
  // Bumped only when the DRAFT doc changes out from under the mounted canvas
  // (Restore) - TagCanvasEditor reads `doc` once, on mount, so a restored
  // draft needs a fresh mount to actually show on the canvas.
  const [editorGeneration, setEditorGeneration] = useState(0);

  const [publishOpen, setPublishOpen] = useState(false);
  const [publishNote, setPublishNote] = useState('');
  const [publishing, setPublishing] = useState(false);

  const [versionsOpen, setVersionsOpen] = useState(false);
  const [viewing, setViewing] = useState<TagTemplateVersionDetail | null>(null);
  const [viewingLoading, setViewingLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    getTemplate(params.id)
      .then((t) => {
        if (!cancelled) {
          setTemplate(t);
          setDraftLayers(t.doc.layers);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load template');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  const handleSave = useCallback(async () => {
    if (!template) return;
    setSaving(true);
    try {
      const updated = await updateTemplate(template.id, { ...template.doc, layers: draftLayers });
      setTemplate(updated);
      toast.success('Template saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save template');
    } finally {
      setSaving(false);
    }
  }, [template, draftLayers]);

  const handlePublish = useCallback(async () => {
    if (!template) return;
    setPublishing(true);
    try {
      const updated = await publishTemplate(template.id, publishNote.trim() || undefined);
      setTemplate(updated);
      setPublishOpen(false);
      setPublishNote('');
      toast.success(`Published v${updated.published_version_no}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not publish template');
    } finally {
      setPublishing(false);
    }
  }, [template, publishNote]);

  const handleView = useCallback(
    async (versionId: string) => {
      if (!template) return;
      setViewingLoading(true);
      try {
        const detail = await getTemplateVersion(template.id, versionId);
        setViewing(detail);
        setVersionsOpen(false);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Could not load version');
      } finally {
        setViewingLoading(false);
      }
    },
    [template],
  );

  const handleRestoreFromSheet = useCallback(
    async (versionId: string) => {
      if (!template) return;
      const updated = await restoreTemplateVersion(template.id, versionId);
      setTemplate(updated);
      setDraftLayers(updated.doc.layers);
      setEditorGeneration((n) => n + 1);
      setViewing(null);
      toast.success('Draft restored');
    },
    [template],
  );

  const handleRestoreFromViewer = useCallback(async () => {
    if (!template || !viewing) return;
    try {
      const updated = await restoreTemplateVersion(template.id, viewing.id);
      setTemplate(updated);
      setDraftLayers(updated.doc.layers);
      setEditorGeneration((n) => n + 1);
      setViewing(null);
      toast.success('Draft restored');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not restore version');
    }
  }, [template, viewing]);

  if (isLoading) {
    return (
      <Container>
        <PageHeader title={<Skeleton className="h-6 w-48" />} crumbTitle="Loading" />
        <Skeleton className="mt-4 h-[400px] w-full" />
      </Container>
    );
  }

  if (error || !template) {
    return (
      <Container>
        <PageHeader
          title="Template not found"
          actions={
            <BackToList listPath="/dealer-kit/tag-templates" label="Back to templates" />
          }
        />
        <p className="mt-4 text-sm text-destructive">{error ?? 'Template not found'}</p>
      </Container>
    );
  }

  const isLive = Boolean(template.published_version_id);

  return (
    <div className="flex h-[calc(100dvh-var(--header-height)-20px)] flex-col">
      {/* Header: PageHeader keeps the trail and title one component and one
          scale (S5-01, S5-02) even though this shell sits outside the normal
          scrolling Toolbar rhythm - shrink-0 so the canvas below still gets
          whatever height is left, exactly as the old compact bar did.
          The 100dvh subtracts the fixed top bar's own height (the demo1
          layout's `--header-height`, 70px desktop / 60px below lg) plus the
          `<main>` wrapper's `pt-5` (20px) - both chrome above this div that a
          flat 56px never accounted for and left the canvas short. */}
      <div className="shrink-0 border-b">
        <Container>
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                {template.name}
                <Badge variant={isLive ? 'success' : 'outline'} className="font-normal">
                  {isLive ? `Live v${template.published_version_no}` : 'Draft'}
                </Badge>
              </span>
            }
            actions={
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setVersionsOpen(true)}
                  disabled={viewingLoading}
                >
                  <History className="size-3.5" />
                  Versions
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSave}
                  disabled={saving || Boolean(viewing)}
                >
                  <SaveIcon className="size-3.5" />
                  {saving ? 'Saving...' : 'Save'}
                </Button>
                <Button size="sm" onClick={() => setPublishOpen(true)} disabled={Boolean(viewing)}>
                  <Upload className="size-3.5" />
                  Publish
                </Button>
                <BackToList listPath="/dealer-kit/tag-templates" label="Back to templates" />
              </div>
            }
          />
        </Container>
      </div>

      {/* Canvas editor fills remaining height. Save now lives in the header
          (AC-S5-5), so the canvas's own bottom save bar is hidden here - its
          `onChange` still fires as a fallback, but this host reads layers via
          `onLayersChange` so header Save always has the latest state even
          before that fires. */}
      <div className="flex-1 overflow-hidden">
        {viewing ? (
          <TagVersionViewer
            doc={viewing.doc}
            versionNo={viewing.version_no}
            onBackToDraft={() => setViewing(null)}
            onRestore={handleRestoreFromViewer}
          />
        ) : (
          <TagCanvasEditor
            key={editorGeneration}
            doc={template.doc}
            onChange={(doc) => setDraftLayers(doc.layers)}
            onLayersChange={setDraftLayers}
            hideSaveBar
          />
        )}
      </div>

      <TemplateVersionsSheet
        templateId={template.id}
        open={versionsOpen}
        onOpenChange={setVersionsOpen}
        liveVersionNo={template.published_version_no}
        onView={(versionId) => handleView(versionId)}
        onRestore={handleRestoreFromSheet}
      />

      <Dialog open={publishOpen} onOpenChange={setPublishOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Publish this template</DialogTitle>
            <DialogDescription>
              Creates a new version from the current draft and moves the request
              designer&apos;s live pointer to it. The draft keeps editing normally
              afterwards.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="publish-note">Note (optional)</Label>
            <Textarea
              id="publish-note"
              value={publishNote}
              onChange={(e) => setPublishNote(e.target.value)}
              placeholder="What changed in this version?"
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPublishOpen(false)} disabled={publishing}>
              Cancel
            </Button>
            <Button onClick={handlePublish} disabled={publishing}>
              {publishing ? 'Publishing...' : 'Publish'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
