'use client';

import { useState } from 'react';
import { KeyRound, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';

import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  useDeleteIntegration,
  useIntegrations,
  useIssueKey,
  useRevokeKey,
  useRotateKey,
} from '../hooks/useIntegrations';
import type { Integration, IssuedKey } from '../types/integration.types';
import { IntegrationFormDialog } from './IntegrationFormDialog';
import { IssuedKeyDialog } from './IssuedKeyDialog';

function StatusBadge({ integration }: { integration: Integration }) {
  if (!integration.is_active) return <Badge variant="secondary">Inactive</Badge>;
  if (integration.status === 'ERROR') return <Badge variant="destructive">Error</Badge>;
  if (integration.status === 'ACTIVE') return <Badge variant="success">Active</Badge>;
  // UNVERIFIED is the honest default: the integration exists but has never
  // successfully authenticated, so claiming "Active" would overstate it.
  return <Badge variant="outline">Unverified</Badge>;
}

function KeysPanel({ integration }: { integration: Integration }) {
  const issue = useIssueKey();
  const rotate = useRotateKey();
  const revoke = useRevokeKey();
  const [issued, setIssued] = useState<IssuedKey | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);

  const live = integration.keys.filter((k) => k.is_active);
  const retired = integration.keys.filter((k) => !k.is_active);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={async () => setIssued(await issue.mutateAsync(integration.id))}
          disabled={issue.isPending}
        >
          <KeyRound className="size-4" /> Issue key
        </Button>
        {live.length > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={async () =>
              setIssued(
                await rotate.mutateAsync({ integrationId: integration.id, graceDays: 7 }),
              )
            }
            disabled={rotate.isPending}
          >
            <RefreshCw className="size-4" /> Rotate (7-day grace)
          </Button>
        )}
      </div>

      {integration.keys.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No keys issued. This integration cannot authenticate until one is created.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Key</th>
                <th className="py-2 pr-3 font-medium">Last used</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {[...live, ...retired].map((key) => (
                <tr key={key.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-mono text-xs">{key.key_prefix}…</td>
                  <td className="py-2 pr-3">
                    {/* Whether the caller actually migrated. Without this,
                        closing a grace window is guesswork. */}
                    {key.last_used_at ? (
                      formatDateTimeInMalaysia(key.last_used_at)
                    ) : (
                      <span className="text-muted-foreground">Never used</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    {key.revoked_at ? (
                      <Badge variant="secondary">Revoked</Badge>
                    ) : key.expires_at && !key.is_active ? (
                      <Badge variant="secondary">Expired</Badge>
                    ) : key.expires_at ? (
                      <Badge variant="outline">
                        Expires {formatDateTimeInMalaysia(key.expires_at)}
                      </Badge>
                    ) : (
                      <Badge variant="success">Active</Badge>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right">
                    {key.is_active && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setConfirmRevoke(key.id)}
                      >
                        Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <IssuedKeyDialog issued={issued} onClose={() => setIssued(null)} />

      {/* Revoking is destructive and immediate — never one click. */}
      <ConfirmDeleteDialog
        open={!!confirmRevoke}
        onOpenChange={(open) => !open && setConfirmRevoke(null)}
        title="Revoke this key?"
        description="The key stops working immediately. Any caller still using it will fail to authenticate until it is replaced. This action cannot be undone."
        successMessage="Key revoked"
        onDelete={async () => {
          if (confirmRevoke) {
            await revoke.mutateAsync({
              integrationId: integration.id,
              keyId: confirmRevoke,
            });
          }
        }}
        onSuccess={() => setConfirmRevoke(null)}
      />
    </div>
  );
}

export function IntegrationsView() {
  const { data: integrations, isLoading, isError, error } = useIntegrations();
  const remove = useDeleteIntegration();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Integration | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Integration | null>(null);

  if (isLoading) {
    return <p className="p-6 text-sm text-muted-foreground">Loading integrations…</p>;
  }

  if (isError) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">
          {(error as Error)?.message ?? 'Failed to load integrations'}
        </p>
      </div>
    );
  }

  const rows = integrations ?? [];

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Integrations</h1>
          <p className="text-sm text-muted-foreground">
            Systems that call Sorento with an API key. Each one authenticates as its own
            user, so its role decides what it can reach.
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus className="size-4" /> Add integration
        </Button>
      </div>

      {rows.length === 0 ? (
        // Explicit empty state with a next step, never a blank panel.
        <Card>
          <CardContent className="py-10 text-center">
            <p className="font-medium">No integrations yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Add one to give a system its own API key, instead of sharing a single
              credential between callers.
            </p>
            <Button
              className="mt-4"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <Plus className="size-4" /> Add integration
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {rows.map((integration) => (
            <Card key={integration.id}>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <CardTitle className="flex flex-wrap items-center gap-2">
                    <span className="truncate" title={integration.name}>
                      {integration.name}
                    </span>
                    <StatusBadge integration={integration} />
                    <Badge variant="outline">{integration.type}</Badge>
                  </CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Acts as{' '}
                    {integration.act_as_user_name ? (
                      <span className="font-medium">{integration.act_as_user_name}</span>
                    ) : (
                      // Fails closed at the auth layer; say so rather than
                      // leaving a blank that reads as "fine".
                      <span className="text-destructive">
                        no principal — this integration cannot authenticate
                      </span>
                    )}
                    {' · '}
                    {integration.last_used_at
                      ? `last used ${formatDateTimeInMalaysia(integration.last_used_at)}`
                      : 'never used'}
                  </p>
                  {integration.last_error && (
                    <p className="mt-1 text-sm text-destructive">
                      Last error: {integration.last_error}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setEditing(integration);
                      setFormOpen(true);
                    }}
                  >
                    <Pencil className="size-4" /> Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setConfirmDelete(integration)}
                  >
                    <Trash2 className="size-4" /> Delete
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <KeysPanel integration={integration} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <IntegrationFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        integration={editing}
      />

      <ConfirmDeleteDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
        title="Confirm delete"
        description={
          confirmDelete
            ? `Delete "${confirmDelete.name}" and all ${confirmDelete.keys.length} of its API key(s). Any caller using them will stop authenticating immediately. This action cannot be undone.`
            : ''
        }
        successMessage="Integration deleted"
        onDelete={async () => {
          if (confirmDelete) await remove.mutateAsync(confirmDelete.id);
        }}
        onSuccess={() => setConfirmDelete(null)}
      />
    </div>
  );
}
