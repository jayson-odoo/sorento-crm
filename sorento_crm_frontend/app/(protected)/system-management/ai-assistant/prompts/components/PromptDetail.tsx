'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, GitCompare, Loader2, Save } from 'lucide-react';
import { toast } from 'sonner';
import { useHasPermission } from '@/hooks/usePermissions';
import { cn } from '@/lib/utils';
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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Container } from '@/components/common/container';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableTextarea } from '@/components/common/find-in-text/SearchableTextarea';
import {
  usePromptVersion,
  usePromptVersions,
  useSaveVersion,
  useSetLabel,
} from '../../hooks/useAIAssistantPrompts';
import { validateVars } from '../../lib/promptVars';
import type { SaveVersionError } from '../../services/aiPromptsService';
import { AgentModelCard } from './AgentModelCard';
import { DiffView } from './DiffView';
import { DryRunBox } from './DryRunBox';
import { PublishDialog } from './PublishDialog';
import { VarChips } from './VarChips';

const EDIT_PERMISSION = 'system.ai_assistant_settings.edit';

export function PromptDetail({ name }: { name: string }) {
  const versionsQuery = usePromptVersions(name);
  const canEdit = useHasPermission(EDIT_PERMISSION);

  const meta = versionsQuery.data;
  const productionVersion = meta?.labels.production ?? meta?.versions[0]?.version ?? null;

  // Which version is loaded as the editor base. Defaults to production.
  const [baseVersion, setBaseVersion] = useState<number | null>(null);
  useEffect(() => {
    if (baseVersion == null && productionVersion != null) setBaseVersion(productionVersion);
  }, [productionVersion, baseVersion]);

  const baseQuery = usePromptVersion(name, baseVersion);
  const [draft, setDraft] = useState<string>('');
  const [commitMessage, setCommitMessage] = useState('');
  const [loadedFor, setLoadedFor] = useState<string>(''); // `${name}:${version}` currently in the buffer

  // Load the fetched base template into the draft buffer once per version load.
  useEffect(() => {
    if (baseQuery.data && loadedFor !== `${name}:${baseQuery.data.version}`) {
      setDraft(baseQuery.data.template);
      setLoadedFor(`${name}:${baseQuery.data.version}`);
    }
  }, [baseQuery.data, name, loadedFor]);

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

  const declared = meta?.variables ?? [];
  const validation = useMemo(() => validateVars(draft, declared), [draft, declared]);
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
    label: 'production' | 'staging';
  }>({ open: false, version: null, versionId: null, label: 'production' });

  // Version-switch discard confirm (AlertDialog, never window.confirm — CRUD UX
  // standard / feedback_confirm_before_delete_or_unlink).
  const [pendingSwitch, setPendingSwitch] = useState<number | null>(null);

  const saveInputRef = useRef<HTMLInputElement>(null);

  const switchToVersion = (version: number) => {
    setBaseVersion(version);
    setLoadedFor('');
  };

  const requestSwitch = (version: number) => {
    if (version === baseVersion) return;
    if (dirty) {
      setPendingSwitch(version);
      return;
    }
    switchToVersion(version);
  };

  if (versionsQuery.isLoading) {
    return (
      <Container>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading…
        </div>
      </Container>
    );
  }
  if (versionsQuery.isError || !meta) {
    return (
      <Container>
        <p className="text-sm text-destructive">
          {(versionsQuery.error as Error)?.message || 'Failed to load prompt'}
        </p>
      </Container>
    );
  }

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
            toast.warning(`Saved v${v.version}. Note: declared var(s) not used — ${missing.join(', ')}`);
          } else {
            toast.success(`Saved v${v.version}`);
          }
          setCommitMessage('');
          setBaseVersion(v.version);
          setLoadedFor(''); // force reload of the new version into the buffer
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

  return (
    <Container className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <Link
            href="/system-management/ai-assistant/prompts"
            className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> All prompts
          </Link>
          <h1 className="flex items-center gap-2 text-xl font-semibold break-words">
            <span className="font-mono">{name}</span>
            {!meta.active ? (
              <Badge variant="warning" className="text-xs">
                Dormant · activates in {meta.activates_in}
              </Badge>
            ) : null}
          </h1>
          <p className="text-sm text-muted-foreground break-words">{meta.role}</p>
        </div>
      </div>

      {!meta.active ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
          Inactive — this prompt is saved but not used at runtime yet. It activates in milestone{' '}
          {meta.activates_in}. You can draft ahead; dry-run is disabled until it has a call site.
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-4">
        <AgentModelCard name={name} canEdit={canEdit} />

        {/* Version history */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="text-base">Version history</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {meta.versions.map((v) => {
              const isBase = v.version === baseVersion;
              return (
                // Not a <button>: it holds real Publish/Stage <button>s (invalid
                // to nest interactive-in-interactive). Clickable div + keyboard.
                <div
                  key={v.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => requestSwitch(v.version)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      requestSwitch(v.version);
                    }
                  }}
                  className={cn(
                    'w-full cursor-pointer rounded-md border p-2 text-left text-xs transition',
                    isBase ? 'border-primary bg-primary/5' : 'hover:bg-muted/50',
                  )}
                  data-testid={`version-row-${v.version}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">v{v.version}</span>
                    <span className="flex gap-1">
                      {v.labels.includes('production') ? (
                        <Badge variant="success" className="text-[10px]">
                          ● production
                        </Badge>
                      ) : null}
                      {v.labels.includes('staging') ? (
                        <Badge variant="warning" className="text-[10px]">
                          staging
                        </Badge>
                      ) : null}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-muted-foreground" title={v.commit_message || ''}>
                    {v.commit_message || <span className="italic">(no message)</span>}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {v.created_by_name || 'unknown'}
                  </p>
                  {canEdit && meta.active ? (
                    <div className="mt-2 flex gap-1">
                      {!v.labels.includes('production') ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setPublishState({ open: true, version: v.version, versionId: v.id, label: 'production' });
                          }}
                          className="rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] font-medium text-white hover:bg-emerald-700"
                          data-testid={`publish-production-${v.version}`}
                        >
                          Publish
                        </button>
                      ) : null}
                      {!v.labels.includes('staging') ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setPublishState({ open: true, version: v.version, versionId: v.id, label: 'staging' });
                          }}
                          className="rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-medium text-white hover:bg-amber-600"
                          data-testid={`publish-staging-${v.version}`}
                        >
                          Stage
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </CardContent>
        </Card>
        </div>

        {/* Editor + tools */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">
                Editor{' '}
                <span className="text-xs font-normal text-muted-foreground">
                  (base: v{baseVersion}
                  {dirty ? ' · unsaved changes' : ''})
                </span>
              </CardTitle>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setDiffOpen((o) => !o);
                  if (diffAgainst == null) {
                    const other = meta.versions.find((v) => v.version !== baseVersion);
                    setDiffAgainst(other?.version ?? baseVersion);
                  }
                }}
                data-testid="diff-toggle"
              >
                <GitCompare className="size-4" /> {diffOpen ? 'Hide diff' : 'Diff'}
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <SearchableTextarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="min-h-[320px] font-mono text-xs"
                spellCheck={false}
                disabled={!canEdit}
                data-testid="prompt-editor"
              />
              <VarChips validation={validation} declared={declared} />

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
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="size-3 animate-spin" /> Loading…
                    </div>
                  )}
                </div>
              ) : null}

              {canEdit ? (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <div className="flex-1 space-y-1">
                    <label className="text-xs text-muted-foreground">Commit message (required)</label>
                    <Input
                      ref={saveInputRef}
                      value={commitMessage}
                      onChange={(e) => setCommitMessage(e.target.value)}
                      placeholder="What changed and why?"
                      data-testid="commit-message"
                    />
                  </div>
                  <Button
                    type="button"
                    onClick={doSave}
                    disabled={saveMut.isPending || hasUnknownTokens || !commitMessage.trim() || !dirty}
                    data-testid="save-version"
                  >
                    {saveMut.isPending ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <>
                        <Save className="size-4" /> Save as new version
                      </>
                    )}
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">You have read-only access to prompts.</p>
              )}
            </CardContent>
          </Card>

          <DryRunBox
            keyName={name}
            versionId={baseVersionId}
            versionLabel={`v${baseVersion}`}
            disabled={!meta.active}
            disabledReason={
              meta.active ? undefined : `Dormant key — no runtime call site until ${meta.activates_in}.`
            }
          />
        </div>
      </div>

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
