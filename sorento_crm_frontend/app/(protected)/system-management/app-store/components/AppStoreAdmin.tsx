'use client';

import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { TENANT_MODULES_QUERY_KEY, useTenantModules } from '@/hooks/useTenantModules';
import {
  disableModule,
  downloadModuleZip,
  enableModule,
  fetchModuleInstallEvents,
  installModulesOrBundle,
  MODULES_WITH_DATA_PURGE,
  triggerBlobDownload,
  uninstallModule,
  uploadModule,
  activateUploadedModule,
  MODULE_PURGE_TABLES,
  type TenantModuleState,
} from '../services/appModulesService';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import type { ModuleInstallEvent } from '../services/appModulesService';

export default function AppStoreAdmin() {
  const queryClient = useQueryClient();
  const canManage = useHasPermission('system.modules.manage');
  const { raw, refetch } = useTenantModules();
  const [bundleKey, setBundleKey] = useState<string>('');
  const [eventsRowSelection, setEventsRowSelection] = useState<RowSelectionState>({});

  const eventsQuery = useQuery({
    queryKey: ['module-install-events'],
    queryFn: () => fetchModuleInstallEvents({ limit: 50 }),
    enabled: canManage,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: TENANT_MODULES_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ['module-install-events'] });
  };

  const installBundleMut = useMutation({
    mutationFn: (key: string) => installModulesOrBundle({ bundle_key: key }),
    onSuccess: (data) => {
      toast.success(`Installed: ${data.plan.join(', ')}`);
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const installModuleMut = useMutation({
    mutationFn: (keys: string[]) => installModulesOrBundle({ module_keys: keys }),
    onSuccess: (data) => {
      toast.success(`Plan: ${data.plan.join(' → ')}`);
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const enableMut = useMutation({
    mutationFn: (key: string) => enableModule(key),
    onSuccess: (_, key) => {
      toast.success(`Enabled ${key}`);
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const disableMut = useMutation({
    mutationFn: (key: string) => disableModule(key),
    onSuccess: (_, key) => {
      toast.success(`Disabled ${key}`);
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const uninstallMut = useMutation({
    mutationFn: ({
      key,
      confirmation,
      purge,
    }: {
      key: string;
      confirmation: string;
      purge: boolean;
    }) => uninstallModule(key, confirmation, purge),
    onSuccess: (data) => {
      const extra =
        data.purge_data && data.rows_deleted
          ? ` Deleted rows: ${Object.entries(data.rows_deleted)
              .map(([k, v]) => `${k}=${v}`)
              .join(', ')}`
          : '';
      toast.success((data.message || 'Uninstalled') + extra);
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const bundles = raw?.bundles ?? [];
  const sortedModules = useMemo(() => {
    const modules = raw?.modules ?? [];
    return [...modules].sort((a, b) => a.display_name.localeCompare(b.display_name));
  }, [raw?.modules]);

  const busy =
    installModuleMut.isPending ||
    enableMut.isPending ||
    disableMut.isPending ||
    uninstallMut.isPending ||
    installBundleMut.isPending;

  const eventColumns = useMemo<ColumnDef<ModuleInstallEvent>[]>(
    () => [
      buildSelectColumn<ModuleInstallEvent>(),
      {
        id: 'created_at',
        accessorFn: (row) => row.created_at ?? null,
        header: ({ column }) => <DataGridColumnHeader title="When" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'When', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-xs">{row.original.created_at ?? '-'}</span>
        ),
      },
      {
        id: 'module_key',
        accessorFn: (row) => row.module_key,
        header: ({ column }) => <DataGridColumnHeader title="Module" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Module', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => <span>{row.original.module_key}</span>,
      },
      {
        id: 'action',
        accessorFn: (row) => row.action,
        header: ({ column }) => <DataGridColumnHeader title="Action" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Action', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => <span>{row.original.action}</span>,
      },
      {
        id: 'actor_user_id',
        accessorFn: (row) => row.actor_user_id ?? null,
        header: ({ column }) => <DataGridColumnHeader title="Actor" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Actor', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground">{row.original.actor_user_id ?? '-'}</span>
        ),
      },
    ],
    [],
  );

  const eventsTable = useReactTable({
    columns: eventColumns,
    data: eventsQuery.data?.items ?? [],
    getRowId: (row) => row.id,
    state: {
      pagination: { pageIndex: 0, pageSize: 10 },
      rowSelection: eventsRowSelection,
    },
    enableRowSelection: true,
    onRowSelectionChange: setEventsRowSelection,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
        {canManage && (
          <ModuleUploadButton
            onUploaded={() => {
              invalidate();
              refetch();
            }}
          />
        )}
      </div>

      {!canManage && (
        <Card className="border-amber-200 bg-amber-50/50 dark:bg-amber-950/20">
          <CardHeader>
            <CardTitle className="text-base">View only</CardTitle>
            <CardDescription>
              You need <code className="text-xs">system.modules.manage</code> to install or change
              modules.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Install bundle</CardTitle>
            <CardDescription>
              Preset editions install all listed modules and dependencies in one action. Bundle
              contents are stored in the database (
              <Link
                href="/system-management/app-store/bundles"
                className="underline underline-offset-2 font-medium text-foreground"
              >
                manage bundles
              </Link>
              ).
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <SearchableSelect
                value={bundleKey}
                onChange={setBundleKey}
                options={bundles.map((b) => ({
                  value: b.bundle_key,
                  label: `${b.display_name} (${b.module_keys.length} modules)`,
                }))}
                placeholder="Choose bundle"
              />
            </div>
            <Button
              type="button"
              disabled={!bundleKey || installBundleMut.isPending}
              onClick={() => bundleKey && installBundleMut.mutate(bundleKey)}
            >
              Install bundle
            </Button>
            <Button type="button" variant="outline" asChild>
              <Link href="/system-management/app-store/bundles">Manage bundles</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-4 text-lg font-semibold">Modules</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          <strong>Disable</strong> turns a module off but keeps it installed.{' '}
          <strong>Uninstall</strong> removes it from your tenant; you can add optional data deletion
          (where supported) after typing the module key to confirm.
        </p>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sortedModules.map((m) => (
            <ModuleCard
              key={m.module_key}
              module={m}
              canManage={canManage}
              busy={busy}
              onInstall={() => installModuleMut.mutate([m.module_key])}
              onEnable={() => enableMut.mutate(m.module_key)}
              onDisable={() => disableMut.mutate(m.module_key)}
              onUninstall={async (confirmation, purge) => {
                await uninstallMut.mutateAsync({ key: m.module_key, confirmation, purge });
              }}
            />
          ))}
        </div>
      </div>

      {canManage && (
        <Card>
          <CardHeader className="block space-y-3">
            <div>
              <CardTitle>Recent install events</CardTitle>
              <CardDescription>Audit trail for this tenant.</CardDescription>
            </div>
            <DataGridListToolbar
              table={eventsTable}
              exportConfig={{ filename: 'module_install_events_export.xlsx' }}
              onRefresh={() => void eventsQuery.refetch()}
              isRefreshing={eventsQuery.isFetching && !eventsQuery.isLoading}
            />
          </CardHeader>
          <CardContent>
            {eventsQuery.error ? (
              <p className="text-sm text-destructive">Failed to load events.</p>
            ) : (
              <DataGrid
                table={eventsTable}
                recordCount={eventsQuery.data?.items?.length ?? 0}
                isLoading={eventsQuery.isLoading}
                emptyMessage="No install events"
              >
                <DataGridTable />
              </DataGrid>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ModuleCard({
  module: m,
  canManage,
  busy,
  onInstall,
  onEnable,
  onDisable,
  onUninstall,
}: {
  module: TenantModuleState;
  canManage: boolean;
  busy: boolean;
  onInstall: () => void;
  onEnable: () => void;
  onDisable: () => void;
  onUninstall: (confirmation: string, purge: boolean) => Promise<void>;
}) {
  const [uninstallOpen, setUninstallOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [purgeData, setPurgeData] = useState(false);

  /** Legacy API responses without `installed` assumed fully installed tenants. */
  const installed = m.installed ?? true;

  useEffect(() => {
    if (uninstallOpen) {
      setConfirmText('');
      setPurgeData(false);
    }
  }, [uninstallOpen, m.module_key]);

  const statusBadge = () => {
    if (!installed) return <Badge variant="outline">Not installed</Badge>;
    if (!m.enabled) return <Badge variant="secondary">Installed · Off</Badge>;
    return <Badge>On</Badge>;
  };

  const purgeSupported = MODULES_WITH_DATA_PURGE.includes(m.module_key);
  const purgeInfo = MODULE_PURGE_TABLES[m.module_key];
  const canUninstall = installed && m.module_key !== 'base';

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{m.display_name}</CardTitle>
          {statusBadge()}
        </div>
        <CardDescription className="text-xs line-clamp-3">{m.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {m.dependencies.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Depends on: {m.dependencies.join(', ')}
          </p>
        )}
        {canManage && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={onInstall}
              title="Install module and dependencies"
            >
              {installed ? 'Re-resolve dependencies' : 'Install'}
            </Button>
            {installed && !m.enabled && (
              <Button type="button" size="sm" disabled={busy} onClick={onEnable}>
                Enable
              </Button>
            )}
            {installed && m.enabled && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy || m.module_key === 'base'}
                onClick={onDisable}
              >
                Disable
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy || m.module_key === 'base'}
              title={
                m.module_key === 'base'
                  ? 'Platform module cannot be exported'
                  : 'Download this module as a zip you can drop into another deployment'
              }
              onClick={async () => {
                try {
                  const { blob, filename } = await downloadModuleZip(m.module_key);
                  triggerBlobDownload(blob, filename);
                  toast.success(`Downloaded ${filename}`);
                } catch (e) {
                  toast.error((e as Error).message);
                }
              }}
            >
              Download zip
            </Button>
            {canUninstall && (
              <Button
                type="button"
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => setUninstallOpen(true)}
              >
                Uninstall
              </Button>
            )}
          </div>
        )}
      </CardContent>

      <AlertDialog open={uninstallOpen} onOpenChange={setUninstallOpen}>
        <AlertDialogContent className="max-w-lg">
          <AlertDialogHeader>
            <AlertDialogTitle>Uninstall {m.display_name}?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3 text-left text-sm text-muted-foreground">
                <p>
                  This removes the module from your tenant. You can install it again later (empty or
                  after re-import).
                </p>
                <p>
                  If other installed modules still depend on this one, uninstall will be blocked
                  until you uninstall or change those dependents first (even if a dependent is
                  disabled but still installed).
                </p>
                <div className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
                  <p className="font-medium text-foreground">Module dependencies (catalog)</p>
                  <p className="mt-1">
                    {m.dependencies.length > 0
                      ? `This module depends on: ${m.dependencies.join(', ')}. Those modules are not uninstalled automatically.`
                      : 'This module has no declared dependencies in the catalog.'}
                  </p>
                  <p className="mt-2 text-[11px]">
                    Reverse blocking: any other module that (transitively) depends on{' '}
                    <code className="font-mono">{m.module_key}</code> must be uninstalled first
                    before this one can be removed.
                  </p>
                </div>
                {purgeSupported && purgeInfo ? (
                  <div className="rounded-md border border-amber-200/80 bg-amber-50/60 p-3 text-xs dark:border-amber-900/50 dark:bg-amber-950/30">
                    <p className="font-medium text-foreground">If you delete module data (purge)</p>
                    <p className="mt-1 text-muted-foreground">
                      {purgeInfo.description}
                    </p>
                    <p className="mt-2 font-medium text-foreground">Database tables cleared (in order)</p>
                    <ol className="mt-1 list-decimal pl-4 text-muted-foreground">
                      {purgeInfo.tables.map((t) => (
                        <li key={t}>
                          <code className="font-mono text-[11px]">{t}</code>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : (
                  <div className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
                    <p className="font-medium text-foreground">Data purge</p>
                    <p className="mt-1">
                      There is no automated &quot;delete all tables&quot; path for this module. Uninstall
                      only removes the tenant install flag unless you implement manual cleanup.
                    </p>
                  </div>
                )}
                <div className="space-y-2">
                  <Label htmlFor={`confirm-${m.module_key}`}>
                    Type the module key <code className="font-mono">{m.module_key}</code> to
                    confirm
                  </Label>
                  <Input
                    id={`confirm-${m.module_key}`}
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    autoComplete="off"
                    placeholder={m.module_key}
                  />
                </div>
                <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3">
                  <Checkbox
                    id={`purge-${m.module_key}`}
                    checked={purgeData}
                    onCheckedChange={(v) => setPurgeData(v === true)}
                  />
                  <div className="grid gap-1">
                    <Label htmlFor={`purge-${m.module_key}`} className="cursor-pointer font-medium">
                      Also delete module data from the database
                    </Label>
                    <p className="text-xs">
                      Irreversible. Supported for: {MODULES_WITH_DATA_PURGE.join(', ')}. Other
                      modules: leave unchecked to only remove the install flag, or the server will
                      reject purge.
                      {!purgeSupported && purgeData && (
                        <span className="mt-1 block font-medium text-destructive">
                          «{m.module_key}» does not have automated purge yet - uncheck or expect an
                          error.
                        </span>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
            <Button
              type="button"
              variant="destructive"
              disabled={busy || confirmText.trim() !== m.module_key}
              onClick={async () => {
                try {
                  await onUninstall(confirmText.trim(), purgeData);
                  setUninstallOpen(false);
                } catch {
                  /* toast handled by mutation */
                }
              }}
            >
              Uninstall
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function ModuleUploadButton({ onUploaded }: { onUploaded: () => void }) {
  const [uploading, setUploading] = useState(false);
  const [activating, setActivating] = useState(false);
  const [pickedFile, setPickedFile] = useState<File | null>(null);
  const [needsRebuild, setNeedsRebuild] = useState(false);

  const inputId = 'app-store-module-zip-input';

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPickedFile(f);
    void doUpload(f);
    e.target.value = '';
  };

  const doUpload = async (file: File) => {
    setUploading(true);
    setNeedsRebuild(false);
    try {
      const result = await uploadModule(file);
      toast.success(
        `Uploaded ${result.module_key} v${result.version}. Activating…`,
      );
      setNeedsRebuild(result.needs_frontend_rebuild);
      setActivating(true);
      try {
        await activateUploadedModule(result.module_key);
        toast.success(`Activated ${result.module_key}`);
      } catch (e) {
        toast.error((e as Error).message);
      } finally {
        setActivating(false);
      }
      onUploaded();
      if (result.restart_required) {
        toast.info(
          'Backend restart required for new routes to register.',
          { duration: 8001 },
        );
      }
      if (result.needs_frontend_rebuild) {
        toast.info(
          'New frontend pages added - rebuild the frontend to make them visible.',
          { duration: 10000 },
        );
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUploading(false);
      setPickedFile(null);
    }
  };

  const busy = uploading || activating;

  return (
    <>
      <input
        id={inputId}
        type="file"
        accept=".zip,application/zip"
        className="sr-only"
        onChange={onPick}
        disabled={busy}
      />
      <Label htmlFor={inputId} className="cursor-pointer">
        <Button asChild type="button" size="sm" variant="outline" disabled={busy}>
          <span>{busy ? (activating ? 'Activating…' : 'Uploading…') : 'Upload module'}</span>
        </Button>
      </Label>
      {pickedFile && (
        <span className="text-xs text-muted-foreground">{pickedFile.name}</span>
      )}
      {needsRebuild && (
        <span className="text-xs text-amber-600 dark:text-amber-400">
          Frontend rebuild required
        </span>
      )}
    </>
  );
}
