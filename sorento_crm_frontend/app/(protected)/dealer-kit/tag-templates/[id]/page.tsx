'use client';

/**
 * Tag template editor page.
 *
 * Loads the template by id and renders the full TagCanvasEditor against its
 * DRAFT doc. Save writes the draft (unchanged). Publish persists the current
 * draft first and only then snapshots it into an immutable version and moves
 * the live pointer (S5, PLAN D7) - an unsaved edit publishes exactly like a
 * saved one. The request designer's template source reads only the live
 * pointer's doc, never this draft, so an in-progress edit is never at risk
 * of going live by accident on its own.
 *
 * View, from the Versions sheet, swaps the VISIBLE panel to a read-only
 * render of that version (D16) via `TagVersionViewer` - `TagCanvasEditor`
 * itself stays mounted underneath (merely hidden), because it seeds its
 * internal layer state from `doc` ONCE, on mount: unmounting it to show the
 * viewer and remounting it on Back-to-draft would silently reset any edit
 * made since the last render to whatever `doc` was at that later moment
 * (bug fixed here - Back-to-draft used to throw away unsaved work). Feeding
 * it `{...template.doc, layers: draftLayers}` keeps that seed correct even
 * on a genuine remount (Restore bumps `editorGeneration`).
 *
 * Restore (from the sheet or from the viewer's banner - same action, same
 * handler) runs immediately, no confirmation dialog (PRINCIPLES: a new
 * destructive-confirm dialog is a defect). The draft it overwrites is held
 * in memory first, so the success toast's Undo action can PUT it straight
 * back.
 *
 * Autosave (D22, S8): every committed draft change re-fires `onLayersChange`
 * (`draftLayers` changes), and an effect on THAT schedules a debounced save
 * through the same `updateTemplate` call the header's manual Save makes.
 * Publish is unchanged - it already persists the draft itself before
 * snapshotting it (S1 above), so it always sees the latest edit whether or
 * not autosave has gotten to it yet.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
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
import { cn } from '@/lib/utils';
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
import { FocusShell, FocusToggle } from '../../components/FocusMode';
import { AutosaveIndicator } from '../../components/AutosaveIndicator';
import { useAutosave } from '@/hooks/useAutosave';

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
  // Which version Restore is in flight for - the viewer banner's own button
  // needs to know so it can say "Restoring..." (the sheet tracks its own row
  // locally).
  const [restoringVersionId, setRestoringVersionId] = useState<string | null>(null);

  /** Full screen (D11, AC-S6-1): the same `FocusShell` the room designer uses. */
  const [focus, setFocus] = useState(false);

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

  // -- Autosave (D22, S8) -----------------------------------------------------

  const templateAutosave = useAutosave<TagLayer[]>(async (layers) => {
    if (!template) return;
    const updated = await updateTemplate(template.id, { ...template.doc, layers });
    setTemplate(updated);
  });

  // Every REAL edit to the draft schedules a debounced save. The first time
  // this effect can fire with a LOADED template is the load itself (the
  // `getTemplate().then()` above sets `template` and `draftLayers` together),
  // not an edit - skipped the same way the request designer skips its own
  // initial `doc`. Before the template has loaded, `template` is still null
  // and nothing is scheduled at all (a restore also goes through here, and
  // autosaving its already-persisted doc back is a harmless no-op overwrite,
  // not a bug worth a special case).
  //
  // `template` itself is read through a REF, not a dependency: autosave's own
  // `onSave` calls `setTemplate(updated)` when it lands, and putting `template`
  // in the deps array would make that its own trigger - a successful save
  // reschedules ANOTHER one for the same unchanged layers, forever. Only
  // `draftLayers` changing is a reason to run this.
  //
  // The "is this the load, not an edit" guard compares the VALUE last seen,
  // not a boolean "have I run yet" flag: dev's StrictMode fires a fresh
  // mount's effects twice (mount, cleanup, mount again) to catch effects
  // that are not idempotent, and a boolean flag would already read "yes" on
  // that second firing, autosaving the freshly-loaded (unedited) draft a
  // second time.
  const templateRef = useRef<TagTemplate | null>(null);
  templateRef.current = template;
  const lastSeenLayersRef = useRef<TagLayer[] | undefined>(undefined);
  useEffect(() => {
    if (!templateRef.current) return;
    if (lastSeenLayersRef.current === draftLayers) return;
    const isInitial = lastSeenLayersRef.current === undefined;
    lastSeenLayersRef.current = draftLayers;
    if (isInitial) return;
    templateAutosave.schedule(draftLayers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftLayers, templateAutosave.schedule]);

  // beforeunload covers a refresh, a close and a jump out of the app.
  useEffect(() => {
    const handler = () => {
      void templateAutosave.flush();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateAutosave.flush]);

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
      // Persist the draft FIRST (S1): Publish snapshots the CURRENT draft,
      // including edits made since the last manual Save, not whatever the
      // backend last had saved.
      const saved = await updateTemplate(template.id, { ...template.doc, layers: draftLayers });
      setTemplate(saved);
      const updated = await publishTemplate(saved.id, publishNote.trim() || undefined);
      setTemplate(updated);
      setPublishOpen(false);
      setPublishNote('');
      toast.success(`Published v${updated.published_version_no}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not publish template');
    } finally {
      setPublishing(false);
    }
  }, [template, draftLayers, publishNote]);

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

  // Restore (B2 captain ruling, 2 Sep): runs immediately, no confirm dialog -
  // the sheet's row button and the viewer's banner button both call this
  // same handler. The draft it is about to overwrite is captured first so
  // the success toast's Undo action can PUT it straight back.
  const handleRestore = useCallback(
    async (versionId: string) => {
      if (!template) return;
      const priorDraft = { ...template.doc, layers: draftLayers };
      setRestoringVersionId(versionId);
      try {
        const updated = await restoreTemplateVersion(template.id, versionId);
        setTemplate(updated);
        setDraftLayers(updated.doc.layers);
        setEditorGeneration((n) => n + 1);
        setViewing(null);
        toast.success('Draft restored', {
          action: {
            label: 'Undo',
            onClick: async () => {
              try {
                const reverted = await updateTemplate(template.id, priorDraft);
                setTemplate(reverted);
                setDraftLayers(reverted.doc.layers);
                setEditorGeneration((n) => n + 1);
                toast.success('Restore undone');
              } catch (err) {
                toast.error(err instanceof Error ? err.message : 'Could not undo the restore');
              }
            },
          },
        });
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Could not restore version');
      } finally {
        setRestoringVersionId(null);
      }
    },
    [template, draftLayers],
  );

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
    <FocusShell active={focus} onExit={() => setFocus(false)}>
    <div
      className={cn(
        'flex flex-col',
        // Full screen (D11): `FocusShell`'s own overlay is already 100dvh
        // with no app chrome inside it, so the fixed calc below - which
        // exists to subtract THAT chrome - would leave a dead gap at the
        // bottom instead of filling the window.
        focus ? 'h-full' : 'h-[calc(100dvh-var(--header-height)-20px)]',
      )}
    >
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
              // flex-wrap: at 375px four buttons plus BackToList do not fit
              // one row (S7).
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setVersionsOpen(true)}
                  disabled={viewingLoading}
                >
                  <History className="size-3.5" />
                  Versions
                </Button>
                <AutosaveIndicator
                  status={templateAutosave.status}
                  savedAt={templateAutosave.savedAt}
                  onRetry={templateAutosave.retry}
                />
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
                <FocusToggle active={focus} onToggle={setFocus} label="template" />
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
          before that fires.

          The editor stays MOUNTED the whole time, merely hidden while View
          is open (B1 fix, AC-S5-8): TagCanvasEditor seeds its internal
          layers state from `doc` once, on mount, so unmounting it to show
          the viewer and remounting it on Back-to-draft used to reset any
          edit made since the last render - a silent data loss the version
          viewer's very existence should never cause. */}
      <div className="flex-1 overflow-hidden">
        <div className={viewing ? 'hidden' : 'h-full'}>
          <TagCanvasEditor
            key={editorGeneration}
            doc={{ ...template.doc, layers: draftLayers }}
            onChange={(doc) => setDraftLayers(doc.layers)}
            onLayersChange={setDraftLayers}
            hideSaveBar
          />
        </div>
        {viewing && (
          <TagVersionViewer
            doc={viewing.doc}
            versionNo={viewing.version_no}
            onBackToDraft={() => setViewing(null)}
            onRestore={() => handleRestore(viewing.id)}
            restoring={restoringVersionId === viewing.id}
          />
        )}
      </div>

      <TemplateVersionsSheet
        templateId={template.id}
        open={versionsOpen}
        onOpenChange={setVersionsOpen}
        liveVersionNo={template.published_version_no}
        onView={(versionId) => handleView(versionId)}
        onRestore={handleRestore}
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
              maxLength={500}
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
    </FocusShell>
  );
}
