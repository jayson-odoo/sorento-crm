'use client';

/**
 * One prompt, on the standard record page (AI-PROMPTS-STD-VIEWS, owner 5 Nov).
 *
 * Record header: title + status pill, then pager, gear (actions on the LOADED version) and
 * the one primary button, Edit. An edit session swaps that group for Cancel + Save - Save
 * always writes a NEW immutable version. Below it, line tabs: Prompt (the editor, unchanged
 * inside), Versions (the history in the standard grid), Model, Dry run.
 */

import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import {
  Ellipsis,
  FileText,
  FlaskConical,
  GitCompare,
  History,
  Loader2,
  Save,
  SquarePen,
  Upload,
  Cpu,
} from 'lucide-react';
import { toast } from '@/lib/toast';
import { useHasPermission } from '@/hooks/usePermissions';
import { useUrlTab } from '@/hooks/useUrlTab';
import { cn } from '@/lib/utils';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import BackToList from '@/components/common/BackToList';
import { Container } from '@/components/common/container';
import DetailActions from '@/components/common/DetailActions';
import { PageHeader } from '@/components/common/PageHeader';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import type { RecordAction } from '@/components/common/recordActions';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { SearchableTextarea } from '@/components/common/find-in-text/SearchableTextarea';
import {
  promptsPagerQuery,
  usePromptKeys,
  usePromptVersion,
  usePromptVersions,
  useRegistryVariables,
  useSaveVersion,
  useSetLabel,
} from '../../hooks/useAIAssistantPrompts';
import { validateVars } from '../../lib/promptVars';
import { splitTemplate } from '../../lib/promptSegments';
import { CHATBOT_TURN_PROMPT_KEYS } from '../../services/aiPromptsService';
import type { PromptVersionRow, SaveVersionError } from '../../services/aiPromptsService';
import { AgentModelCard } from './AgentModelCard';
import { DiffView } from './DiffView';
import { DryRunBox } from './DryRunBox';
import { PromptArchitecture } from './PromptArchitecture';
import { PromptChipEditor, type PromptChipEditorHandle } from './PromptChipEditor';
import { PublishDialog } from './PublishDialog';
import { VarChips } from './VarChips';
import { WiredPanel } from './WiredPanel';
// The full-screen overlay the Dealer Kit designers already use (Esc exits, body scroll locked).
import { FocusShell, FocusToggle } from '@/app/(protected)/dealer-kit/components/FocusMode';

const EDIT_PERMISSION = 'system.ai_assistant_settings.edit';
const LIST_PATH = '/system-management/ai-assistant/prompts';
const TABS = ['prompt', 'versions', 'model', 'dry-run'] as const;

type PublishLabel = 'production' | 'staging';

export function PromptDetail({ name }: { name: string }) {
  const versionsQuery = usePromptVersions(name);
  const canEdit = useHasPermission(EDIT_PERMISSION);
  const [tab, setTab] = useUrlTab({ tabs: [...TABS], defaultTab: 'prompt' });

  const meta = versionsQuery.data;
  const productionVersion = meta?.labels.production ?? meta?.versions[0]?.version ?? null;

  // Whether a dry-run of THIS key would exercise the edit. It is a property of the key rather
  // than of a version, and the versions response does not carry it, so it is read off the key
  // list. Unknown reads as runnable: a list still in flight must not tell the user their key is
  // outside the pipeline, and the route refuses a non-runnable key with a 400 in any case. The
  // two chatbot keys run a dry-run chatbot TURN instead (AC-807), so they stay enabled.
  const keysQuery = usePromptKeys();
  const dryRunnable =
    CHATBOT_TURN_PROMPT_KEYS.includes(name) ||
    (keysQuery.data?.find((row) => row.name === name)?.dry_runnable ?? true);

  // Which version is loaded as the editor base. Defaults to production.
  const [baseVersion, setBaseVersion] = useState<number | null>(null);
  useEffect(() => {
    if (baseVersion == null && productionVersion != null) setBaseVersion(productionVersion);
  }, [productionVersion, baseVersion]);

  const baseQuery = usePromptVersion(name, baseVersion);
  const [draft, setDraft] = useState<string>('');
  const [commitMessage, setCommitMessage] = useState('');
  const [loadedFor, setLoadedFor] = useState<string>(''); // `${name}:${version}` currently in the buffer
  // Standard form view: the record opens read-only, Edit starts a session, Save or Cancel ends it.
  const [editing, setEditing] = useState(false);

  // Load the fetched base template into the draft buffer once per version load.
  useEffect(() => {
    if (baseQuery.data && loadedFor !== `${name}:${baseQuery.data.version}`) {
      setDraft(baseQuery.data.template);
      setLoadedFor(`${name}:${baseQuery.data.version}`);
    }
  }, [baseQuery.data, name, loadedFor]);

  // Slice E: a key with no saved version seeds the editor from `meta.fallback_text` (the code
  // default) instead, once per key.
  useEffect(() => {
    if (meta && meta.versions.length === 0 && loadedFor !== `${name}:fallback`) {
      setDraft(meta.fallback_text ?? '');
      setLoadedFor(`${name}:fallback`);
    }
  }, [meta, name, loadedFor]);

  const dirty = !!baseQuery.data && draft !== baseQuery.data.template;

  // Warn on navigate-away when there are unsaved edits (PLAN §9b Q4).
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  const declared = useMemo(() => meta?.variables ?? [], [meta]);
  // PLAN-prompt-dynamic-30sep R5a: tokens the backend fills from registry tables. They are
  // chips in the editor, always known to validation and never "missing".
  const registryNames = useMemo(() => meta?.registry_variables ?? [], [meta]);
  const hasRegistry = registryNames.length > 0;
  const registryQuery = useRegistryVariables(name, hasRegistry);
  const registryRows = useMemo(() => registryQuery.data ?? [], [registryQuery.data]);
  const [editorMode, setEditorMode] = useState<'edit' | 'preview' | 'architecture'>('edit');
  const isParser = name === 'chatbot_semantic_parser';
  // Full screen for the Editor card (owner, 16 Oct: long prompts are hard to read in the box).
  const [focus, setFocus] = useState(false);
  const chipEditorRef = useRef<PromptChipEditorHandle>(null);
  const validation = useMemo(
    () => validateVars(draft, declared, registryNames),
    [draft, declared, registryNames],
  );
  const hasUnknownTokens = validation.unknown.length > 0;

  const saveMut = useSaveVersion(name);
  const labelMut = useSetLabel(name);

  const [diffOpen, setDiffOpen] = useState(false);
  const [diffAgainst, setDiffAgainst] = useState<number | null>(null);
  const diffAgainstQuery = usePromptVersion(name, diffOpen ? diffAgainst : null);

  const [publishState, setPublishState] = useState<{
    open: boolean;
    version: number | null;
    versionId: string | null;
    label: PublishLabel;
  }>({ open: false, version: null, versionId: null, label: 'production' });

  // Version-switch discard confirm (AlertDialog, never window.confirm).
  const [pendingSwitch, setPendingSwitch] = useState<number | null>(null);

  const saveInputRef = useRef<HTMLInputElement>(null);

  const switchToVersion = (version: number) => {
    setBaseVersion(version);
    setLoadedFor('');
    setTab('prompt');
  };

  const requestSwitch = (version: number) => {
    if (version === baseVersion) {
      setTab('prompt');
      return;
    }
    if (dirty) {
      setPendingSwitch(version);
      return;
    }
    switchToVersion(version);
  };

  const canPublish = canEdit && !!meta?.active;
  const openPublish = (row: PromptVersionRow, label: PublishLabel) =>
    setPublishState({ open: true, version: row.version, versionId: row.id, label });

  const versionColumns = useMemo<ColumnDef<PromptVersionRow>[]>(
    () => [
      {
        id: 'version',
        accessorKey: 'version',
        header: 'Version',
        size: 100,
        cell: ({ row }) => (
          <span className="font-medium tabular-nums">
            v{row.original.version}
            {row.original.version === baseVersion ? (
              <span className="ms-1.5 text-xs font-normal text-muted-foreground">(loaded)</span>
            ) : null}
          </span>
        ),
      },
      {
        id: 'labels',
        accessorFn: (r) => r.labels.join(','),
        header: 'Labels',
        size: 170,
        cell: ({ row }) => (
          <span className="flex flex-wrap gap-1">
            {row.original.labels.includes('production') ? (
              <Badge variant="success" appearance="light">
                production
              </Badge>
            ) : null}
            {row.original.labels.includes('staging') ? (
              <Badge variant="warning" appearance="light">
                staging
              </Badge>
            ) : null}
            {row.original.labels.length === 0 ? <span className="text-muted-foreground">-</span> : null}
          </span>
        ),
      },
      {
        id: 'commit_message',
        accessorKey: 'commit_message',
        header: 'Commit message',
        size: 320,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.commit_message ?? ''}>
            {row.original.commit_message || <span className="italic text-muted-foreground">(no message)</span>}
          </span>
        ),
      },
      {
        id: 'created_by_name',
        accessorKey: 'created_by_name',
        header: 'By',
        size: 150,
        cell: ({ row }) => (
          <span className="truncate text-muted-foreground" title={row.original.created_by_name ?? ''}>
            {row.original.created_by_name || '-'}
          </span>
        ),
      },
      {
        id: 'created_at',
        accessorKey: 'created_at',
        header: 'Created',
        size: 180,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{formatDateTimeInMalaysia(row.original.created_at)}</span>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 56,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        cell: ({ row }) => {
          const v = row.original;
          const canProd = canPublish && !v.labels.includes('production');
          const canStage = canPublish && !v.labels.includes('staging');
          if (!canProd && !canStage) return null;
          return (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  className="h-7 w-7"
                  mode="icon"
                  variant="ghost"
                  aria-label={`Actions for v${v.version}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Ellipsis className="size-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="bottom" align="end" onClick={(e) => e.stopPropagation()}>
                {canProd ? (
                  <DropdownMenuItem
                    onClick={() => openPublish(v, 'production')}
                    data-testid={`publish-production-${v.version}`}
                  >
                    Publish v{v.version}
                  </DropdownMenuItem>
                ) : null}
                {canStage ? (
                  <DropdownMenuItem
                    onClick={() => openPublish(v, 'staging')}
                    data-testid={`publish-staging-${v.version}`}
                  >
                    Stage v{v.version}
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          );
        },
      },
    ],
    [baseVersion, canPublish],
  );

  const backLink = <BackToList listPath={LIST_PATH} label="Back to prompts" />;

  if (versionsQuery.isLoading) {
    return (
      <Container>
        <SectionSkeleton rows={6} className="py-6" />
      </Container>
    );
  }
  if (versionsQuery.isError || !meta) {
    return (
      <Container className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <p className="text-sm text-destructive">
          {(versionsQuery.error as Error)?.message || 'Failed to load prompt'}
        </p>
      </Container>
    );
  }

  const beginEdit = () => {
    setCommitMessage('');
    setEditing(true);
    setTab('prompt');
  };

  const cancelEdit = () => {
    // Back to the stored version: the buffer reloads from it.
    setLoadedFor('');
    setCommitMessage('');
    setEditing(false);
  };

  const doSave = () => {
    if (!commitMessage.trim()) {
      toast.error('Commit message is required');
      saveInputRef.current?.focus();
      return;
    }
    if (hasUnknownTokens) {
      toast.error('Remove unknown template tokens before saving');
      return;
    }
    saveMut.mutate(
      { template: draft, commit_message: commitMessage.trim() },
      {
        onSuccess: (v) => {
          const missing = v.missing_vars ?? validation.missing;
          if (missing.length) {
            toast.warning(`Saved v${v.version}. Note: declared var(s) not used - ${missing.join(', ')}`);
          } else {
            toast.success(`Saved v${v.version}`);
          }
          setCommitMessage('');
          setBaseVersion(v.version);
          setLoadedFor(''); // force reload of the new version into the buffer
          setEditing(false);
        },
        onError: (e: Error & { validation?: SaveVersionError }) => {
          if (e.validation?.unknown_tokens?.length) {
            toast.error(`Unknown token(s): ${e.validation.unknown_tokens.join(', ')}`);
          } else {
            toast.error(e.message);
          }
        },
      },
    );
  };

  const doPublish = () => {
    if (!publishState.versionId) return;
    labelMut.mutate(
      { label: publishState.label, version_id: publishState.versionId },
      {
        onSuccess: () => {
          toast.success(`Moved ${publishState.label} to v${publishState.version}`);
          setPublishState((s) => ({ ...s, open: false }));
        },
        onError: (e: Error) => toast.error(e.message),
      },
    );
  };

  const baseVersionId = baseQuery.data?.id ?? null;
  const baseRow = meta.versions.find((v) => v.version === baseVersion);
  const saveDisabled = saveMut.isPending || hasUnknownTokens || !commitMessage.trim() || !dirty;

  const toggleDiff = () => {
    setDiffOpen((o) => !o);
    if (diffAgainst == null) {
      const other = meta.versions.find((v) => v.version !== baseVersion);
      setDiffAgainst(other?.version ?? baseVersion);
    }
  };

  // The gear acts on the LOADED version (what the editor shows), the same pair each Versions
  // row offers for its own version.
  const gearActions: RecordAction[] = [];
  if (canPublish && baseRow) {
    if (!baseRow.labels.includes('production')) {
      gearActions.push({
        key: 'prompt.publish',
        label: `Publish v${baseRow.version}`,
        icon: Upload,
        run: () => openPublish(baseRow, 'production'),
      });
    }
    if (!baseRow.labels.includes('staging')) {
      gearActions.push({
        key: 'prompt.stage',
        label: `Stage v${baseRow.version}`,
        icon: Upload,
        run: () => openPublish(baseRow, 'staging'),
      });
    }
  }
  if (meta.versions.length > 1) {
    gearActions.push({
      key: 'prompt.compare',
      label: diffOpen ? 'Hide diff' : 'Compare versions',
      icon: GitCompare,
      run: () => {
        toggleDiff();
        setTab('prompt');
      },
    });
  }

  const saveButton = (
    <Button type="button" size="sm" onClick={doSave} disabled={saveDisabled} data-testid="save-version">
      {saveMut.isPending ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <>
          <Save className="size-4" /> Save as new version
        </>
      )}
    </Button>
  );

  return (
    <Container className="space-y-4">
      <PageHeader title={<span className="font-mono">{name}</span>} crumbTitle={name} actions={backLink} />

      {/* The record header: what the prompt IS, and what can be done to it. */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="truncate font-mono text-lg" title={name}>
                {name}
              </CardTitle>
              {meta.active ? (
                <Badge status="active">Active</Badge>
              ) : (
                <Badge variant="warning" appearance="light">
                  {meta.activates_in ? `Dormant (activates in ${meta.activates_in})` : 'Dormant'}
                </Badge>
              )}
            </div>
            {/* An edit session states ONE intent: Save or Cancel. */}
            {editing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={cancelEdit}
                  disabled={saveMut.isPending}
                  data-testid="cancel-edit"
                >
                  Cancel
                </Button>
                {focus ? null : saveButton}
              </div>
            ) : (
              <DetailActions
                pager={{
                  ...promptsPagerQuery,
                  detailPath: LIST_PATH,
                  currentId: name,
                  ariaLabel: 'prompt',
                }}
                actions={gearActions.length ? gearActions : undefined}
                primary={
                  canEdit ? (
                    <Button variant="primary" size="sm" className="gap-1.5" onClick={beginEdit} data-testid="edit-prompt">
                      <SquarePen className="size-4" />
                      Edit
                    </Button>
                  ) : undefined
                }
              />
            )}
          </div>
        </CardHeader>
      </Card>

      <Tabs value={tab} onValueChange={(v) => setTab(v as (typeof TABS)[number])} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start">
          <TabsTrigger value="prompt">
            <FileText />
            <span>Prompt</span>
          </TabsTrigger>
          <TabsTrigger value="versions">
            <History />
            <span>Versions</span>
          </TabsTrigger>
          <TabsTrigger value="model">
            <Cpu />
            <span>Model</span>
          </TabsTrigger>
          <TabsTrigger value="dry-run">
            <FlaskConical />
            <span>Dry run</span>
          </TabsTrigger>
        </TabsList>

        {/* forceMount: the editor keeps its draft, caret and full-screen state across tabs. */}
        <TabsContent
          value="prompt"
          forceMount
          hidden={tab !== 'prompt'}
          className="mt-0 space-y-4 focus-visible:outline-none"
        >
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Prompt</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="Prompt" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Role</div>
                <div className="break-words text-sm" data-testid="prompt-role">
                  {meta.role}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Versions</div>
                <div className="text-sm tabular-nums">
                  Production {meta.labels.production != null ? `v${meta.labels.production}` : '-'} · Staging{' '}
                  {meta.labels.staging != null ? `v${meta.labels.staging}` : '-'}
                </div>
              </div>
            </section>
          </Card>

          <div
            className={cn(
              'grid gap-4',
              hasRegistry && '2xl:grid-cols-[minmax(0,1fr)_300px]',
            )}
          >
            {/* gap, not space-y: the full-screen wrapper around the card is `display: contents`. */}
            <div className="flex min-w-0 flex-col gap-4">
              <FocusShell active={focus} onExit={() => setFocus(false)} keepMounted>
                <Card className={cn(focus && 'mb-8 flex-auto')}>
                  <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-base">
                      Editor{' '}
                      <span className="text-xs font-normal text-muted-foreground">
                        {/* Slice E: no saved version means the draft came off `fallback_text`. */}
                        (base: {meta.versions.length === 0 ? 'code default' : `v${baseVersion}`}
                        {dirty ? ' · unsaved changes' : ''})
                      </span>
                    </CardTitle>
                    <div className="flex flex-wrap items-center gap-2">
                      {/* Full screen covers the record header, so its actions come along. */}
                      {focus && editing ? saveButton : null}
                      {focus && !editing && canPublish && baseRow ? (
                        // The reason sits on a wrapper: a disabled Button takes no pointer events.
                        <span
                          className="flex flex-wrap items-center gap-2"
                          title={dirty ? 'Save first: this publishes the saved version, not the unsaved edits' : undefined}
                        >
                          {!baseRow.labels.includes('staging') ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => openPublish(baseRow, 'staging')}
                              disabled={dirty}
                              data-testid="fullscreen-publish-staging"
                            >
                              Stage v{baseRow.version}
                            </Button>
                          ) : null}
                          {!baseRow.labels.includes('production') ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => openPublish(baseRow, 'production')}
                              disabled={dirty}
                              data-testid="fullscreen-publish-production"
                            >
                              Publish v{baseRow.version}
                            </Button>
                          ) : null}
                        </span>
                      ) : null}
                      <Button type="button" variant="outline" size="sm" onClick={toggleDiff} data-testid="diff-toggle">
                        <GitCompare className="size-4" /> {diffOpen ? 'Hide diff' : 'Diff'}
                      </Button>
                      <FocusToggle active={focus} onToggle={setFocus} label="editor" />
                    </div>
                  </CardHeader>
                  <CardContent className={cn('space-y-3', focus && 'flex flex-auto flex-col')}>
                    {hasRegistry || isParser ? (
                      <Tabs
                        value={editorMode}
                        onValueChange={(v) => setEditorMode(v as 'edit' | 'preview' | 'architecture')}
                      >
                        <TabsList shape="pill" size="sm" aria-label="Editor mode">
                          <TabsTrigger value="edit" data-testid="editor-mode-edit">
                            Edit
                          </TabsTrigger>
                          {hasRegistry ? (
                            <TabsTrigger value="preview" data-testid="editor-mode-preview">
                              Preview rendered prompt
                            </TabsTrigger>
                          ) : null}
                          {isParser ? (
                            <TabsTrigger value="architecture" data-testid="editor-mode-architecture">
                              Architecture
                            </TabsTrigger>
                          ) : null}
                        </TabsList>
                      </Tabs>
                    ) : null}
                    {isParser && editorMode === 'architecture' && (baseQuery.data?.version ?? baseVersion) != null ? (
                      <PromptArchitecture name={name} version={(baseQuery.data?.version ?? baseVersion) as number} />
                    ) : null}
                    {hasRegistry && editorMode === 'preview' ? (
                      <RenderedPreview template={draft} registryNames={registryNames} rows={registryRows} fill={focus} />
                    ) : null}
                    {hasRegistry ? (
                      // Stays mounted (hidden) under Preview, so the owner's last caret survives a
                      // look at the preview and the wired panel's Insert still lands there.
                      <div
                        hidden={editorMode !== 'edit'}
                        className={cn(focus && 'flex min-h-[360px] grow basis-0 flex-col')}
                        data-testid="chip-editor-pane"
                      >
                        <PromptChipEditor
                          ref={chipEditorRef}
                          value={draft}
                          onChange={setDraft}
                          variables={registryRows}
                          registryNames={registryNames}
                          disabled={!editing}
                          fill={focus}
                        />
                      </div>
                    ) : (
                      <div hidden={editorMode !== 'edit'} className={cn(focus && 'flex grow basis-0 flex-col')}>
                        <SearchableTextarea
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          className={cn('min-h-[320px] font-mono text-xs', focus && 'grow basis-0 resize-none')}
                          containerClassName={cn(focus && 'flex min-h-[320px] grow basis-0 flex-col')}
                          spellCheck={false}
                          disabled={!editing}
                          data-testid="prompt-editor"
                        />
                      </div>
                    )}
                    {editorMode !== 'architecture' ? <VarChips validation={validation} declared={declared} /> : null}

                    {diffOpen ? (
                      <div className="space-y-2 rounded-md border p-3">
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-muted-foreground">Compare current draft against:</span>
                          <div data-testid="diff-base-select">
                            <SearchableSelect
                              value={diffAgainst != null ? String(diffAgainst) : ''}
                              onChange={(v) => setDiffAgainst(Number(v))}
                              options={meta.versions.map((v) => ({
                                value: String(v.version),
                                label: `v${v.version}`,
                              }))}
                              placeholder="Select version"
                              size="sm"
                              triggerClassName="w-28"
                            />
                          </div>
                        </div>
                        {diffAgainstQuery.data ? (
                          <DiffView
                            a={diffAgainstQuery.data.template}
                            b={draft}
                            aLabel={`v${diffAgainstQuery.data.version}`}
                            bLabel={dirty ? 'current draft' : `v${baseVersion}`}
                          />
                        ) : (
                          <SectionSkeleton rows={2} className="text-xs" />
                        )}
                      </div>
                    ) : null}

                    {editing ? (
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground" htmlFor="prompt-commit-message">
                          Commit message (required)
                        </label>
                        <Input
                          id="prompt-commit-message"
                          ref={saveInputRef}
                          value={commitMessage}
                          onChange={(e) => setCommitMessage(e.target.value)}
                          placeholder="What changed and why?"
                          data-testid="commit-message"
                        />
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              </FocusShell>
            </div>

            {hasRegistry ? (
              <div className="min-w-0">
                <WiredPanel
                  variables={registryRows}
                  draft={draft}
                  isLoading={registryQuery.isLoading}
                  canEdit={editing}
                  onInsert={(varName) => {
                    // At the owner's last caret in the editor, never appended at the bottom
                    // (owner hand test #1405, item 2).
                    setEditorMode('edit');
                    chipEditorRef.current?.insertVariable(varName);
                  }}
                />
              </div>
            ) : null}
          </div>
        </TabsContent>

        <TabsContent value="versions" className="mt-0 focus-visible:outline-none">
          <PanelDataGrid<PromptVersionRow>
            title="Versions"
            columns={versionColumns}
            rows={meta.versions}
            getRowId={(row) => row.id}
            listingKey={null}
            sortable
            emptyTitle="No saved version yet."
            onRowClick={(row) => requestSwitch(row.version)}
            rowAttributes={(row) => ({ 'data-testid': `version-row-${row.version}` })}
          />
        </TabsContent>

        <TabsContent value="model" className="mt-0 focus-visible:outline-none">
          <AgentModelCard name={name} canEdit={canEdit} />
        </TabsContent>

        <TabsContent value="dry-run" className="mt-0 focus-visible:outline-none">
          <DryRunBox
            keyName={name}
            versionId={baseVersionId}
            versionLabel={`v${baseVersion}`}
            disabled={!meta.active || !dryRunnable}
            disabledReason={
              !meta.active
                ? `Dormant key - no runtime call site until ${meta.activates_in}.`
                : !dryRunnable
                  ? 'This key is not part of the assistant pipeline - the dry-run would not exercise it.'
                  : undefined
            }
          />
        </TabsContent>
      </Tabs>

      <PublishDialog
        open={publishState.open}
        onOpenChange={(o) => setPublishState((s) => ({ ...s, open: o }))}
        keyName={name}
        version={publishState.version}
        label={publishState.label}
        pending={labelMut.isPending}
        onConfirm={doPublish}
      />

      <AlertDialog open={pendingSwitch != null} onOpenChange={(o) => !o && setPendingSwitch(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard unsaved edits?</AlertDialogTitle>
            <AlertDialogDescription>
              You have unsaved changes in the editor. Loading v{pendingSwitch} will discard them. This cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (pendingSwitch != null) switchToVersion(pendingSwitch);
                setPendingSwitch(null);
              }}
            >
              Discard &amp; load v{pendingSwitch}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Container>
  );
}

/** Malaysia time, in the form the chatbot's `{{current_date}}` directive uses ("Wednesday, 30 September 2026"). */
function todayInMalaysia(): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', { // date-format-ok: mirrors the model's own {{current_date}} text (Wednesday, 30 September 2026), not a CRM date display
      timeZone: 'Asia/Kuala_Lumpur',
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    })
      .formatToParts(new Date())
      .map((p) => [p.type, p.value]),
  );
  return `${parts.weekday}, ${parts.day} ${parts.month} ${parts.year}`;
}

/**
 * "Preview rendered prompt" (R5a): the draft with every registry variable replaced by the
 * text the model receives right now, each lightly tinted so its source stays visible.
 * Read-only; `{{current_date}}` shows today.
 */
function RenderedPreview({
  template,
  registryNames,
  rows,
  fill = false,
}: {
  template: string;
  registryNames: string[];
  rows: { name: string; label: string; rendered: string }[];
  /** Full screen: grow to the card's height instead of the 70dvh cap. */
  fill?: boolean;
}) {
  const byName = new Map(rows.map((r) => [r.name, r]));
  return (
    <pre
      data-testid="prompt-preview"
      aria-readonly="true"
      className={cn(
        'max-h-[70dvh] min-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/20 p-3 font-mono text-xs leading-relaxed',
        fill && 'max-h-none grow basis-0',
      )}
    >
      {splitTemplate(template, registryNames).map((seg, i) =>
        seg.kind === 'text' ? (
          <span key={i}>
            <HeadedText text={seg.text.replace(/\{\{\s*current_date\s*\}\}/g, todayInMalaysia())} />
          </span>
        ) : (
          <span key={i} className="rounded-sm bg-primary/10" title={byName.get(seg.name)?.label ?? seg.name}>
            {byName.get(seg.name)?.rendered ?? ''}
          </span>
        ),
      )}
    </pre>
  );
}

/**
 * A line that reads as a section header in a long prompt: a markdown heading ("# Output"), a
 * banner ("== PRICE TERMINOLOGY ==", the chatbot parser's own style) or a short ALL-CAPS line,
 * optionally ending in a colon ("RULES:"). Bold, so the eye can scan.
 */
const HEADING_LINE = /^(#{1,6}\s+\S.*|={2,}\s.*\s={2,}|[A-Z][A-Z0-9 _&/()-]{2,60}:?)$/;

function HeadedText({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, i) => (
        <Fragment key={i}>
          {i > 0 ? '\n' : null}
          {HEADING_LINE.test(line.trim()) ? (
            <span data-heading className="font-semibold text-foreground">
              {line}
            </span>
          ) : (
            line
          )}
        </Fragment>
      ))}
    </>
  );
}
