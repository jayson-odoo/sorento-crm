'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, KeyRound, Pencil, Plug, RefreshCw, Trash2 } from 'lucide-react';

import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/common/PageHeader';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  useDeleteIntegration,
  useIntegration,
  useIssueKey,
  useRevokeKey,
  useRotateKey,
} from '../hooks/useIntegrations';
import type { Integration, IssuedKey } from '../types/integration.types';
import { IntegrationFormDialog } from './IntegrationFormDialog';
import { IssuedKeyDialog } from './IssuedKeyDialog';
import { StatusCell } from './IntegrationsView';

/** A label/value row. Always rendered, with an explicit dash when unset. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-b py-4 last:border-0 sm:flex-row sm:gap-6">
      <div className="w-full text-sm text-muted-foreground sm:w-56 sm:shrink-0">{label}</div>
      <div className="min-w-0 flex-1 text-sm break-words">{children}</div>
    </div>
  );
}

const EMPTY = <span className="text-muted-foreground"> - </span>;

function KeysCard({ integration }: { integration: Integration }) {
  const issue = useIssueKey();
  const rotate = useRotateKey();
  const revoke = useRevokeKey();
  const [issued, setIssued] = useState<IssuedKey | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);

  const live = integration.keys.filter((k) => k.is_active);
  const retired = integration.keys.filter((k) => !k.is_active);

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <CardTitle>API keys</CardTitle>
        <div className="flex flex-wrap gap-2">
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
                  await rotate.mutateAsync({
                    integrationId: integration.id,
                    graceDays: 7,
                  }),
                )
              }
              disabled={rotate.isPending}
            >
              <RefreshCw className="size-4" /> Rotate (7-day grace)
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {integration.keys.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
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
                        <Badge variant="secondary" appearance="light" size="sm">
                          Revoked
                        </Badge>
                      ) : key.expires_at && !key.is_active ? (
                        <Badge variant="secondary" appearance="light" size="sm">
                          Expired
                        </Badge>
                      ) : key.expires_at ? (
                        <Badge variant="warning" appearance="light" size="sm">
                          Expires {formatDateTimeInMalaysia(key.expires_at)}
                        </Badge>
                      ) : (
                        <Badge variant="success" appearance="light" size="sm">
                          Active
                        </Badge>
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
      </CardContent>

      <IssuedKeyDialog issued={issued} onClose={() => setIssued(null)} />

      {/* Revoking is destructive and immediate - never one click. */}
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
    </Card>
  );
}

export function IntegrationDetailView({ id }: { id: string }) {
  const router = useRouter();
  const { data: integration, isLoading, isError, error } = useIntegration(id);
  const remove = useDeleteIntegration();
  const [editOpen, setEditOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (isLoading) {
    return <p className="p-6 text-sm text-muted-foreground">Loading integration…</p>;
  }
  if (isError || !integration) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">
          {(error as Error)?.message ?? 'Integration not found'}
        </p>
        <Link
          href="/integration-management/integrations"
          className="mt-3 inline-block text-sm underline"
        >
          Back to integrations
        </Link>
      </div>
    );
  }

  const config = (integration.config_json ?? {}) as Record<string, unknown>;
  const outboundUrl = (config.base_url as string) || '';
  const rateLimit = config.rate_limit_per_minute as number | undefined;

  return (
    <div className="space-y-4 p-4 md:p-6">
      <PageHeader
        title={integration.name}
        actions={
          <>
            <Button variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="size-4" /> Edit
            </Button>
            <Button variant="outline" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="size-4" /> Delete
            </Button>
            <Button variant="outline" asChild>
              <Link href="/integration-management/integrations">
                <ArrowLeft className="size-4" /> Back to integrations
              </Link>
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{integration.type}</p>
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Plug className="size-4" /> Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <Field label="Name">{integration.name}</Field>
          <Field label="Type">{integration.type}</Field>
          <Field label="Acts as">
            {integration.act_as_user_name ?? (
              <span className="text-destructive">
                No principal - this integration cannot authenticate
              </span>
            )}
          </Field>
          <Field label="Outbound base URL">
            {outboundUrl ? (
              <span className="font-mono text-xs">{outboundUrl}</span>
            ) : (
              // Only meaningful for integrations Sorento calls out to.
              <span className="text-muted-foreground">
                Not set - Sorento cannot push documents or events to this system
              </span>
            )}
          </Field>
          <Field label="Outbound credential">
            {integration.has_credentials ? (
              // Masked, never fetched. The API has no endpoint that returns it.
              <span className="font-mono">••••••••</span>
            ) : (
              <span className="text-muted-foreground">Not set</span>
            )}
          </Field>
          <Field label="Rate limit">
            {rateLimit === 0 ? (
              <span className="text-muted-foreground">Disabled - no ceiling applied</span>
            ) : rateLimit ? (
              `${rateLimit} requests/minute`
            ) : (
              <span className="text-muted-foreground">Default (600/minute)</span>
            )}
          </Field>
          <Field label="Status">
            <StatusCell integration={integration} />
          </Field>
          <Field label="Last used">
            {integration.last_used_at
              ? formatDateTimeInMalaysia(integration.last_used_at)
              : EMPTY}
          </Field>
          <Field label="Last error">
            {integration.last_error ? (
              <span className="text-destructive">{integration.last_error}</span>
            ) : (
              EMPTY
            )}
          </Field>
          <Field label="Created">{formatDateTimeInMalaysia(integration.created_at)}</Field>
        </CardContent>
      </Card>

      <KeysCard integration={integration} />

      <IntegrationFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        integration={integration}
      />

      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Confirm delete"
        description={`Delete "${integration.name}" and all ${integration.keys.length} of its API key(s). Any caller using them will stop authenticating immediately. This action cannot be undone.`}
        successMessage="Integration deleted"
        onDelete={async () => {
          await remove.mutateAsync(integration.id);
        }}
        onSuccess={() => router.push('/integration-management/integrations')}
      />
    </div>
  );
}
