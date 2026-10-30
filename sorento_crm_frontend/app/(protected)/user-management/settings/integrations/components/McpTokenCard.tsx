'use client';

import { useState } from 'react';
import { CopyIcon, LoaderCircleIcon } from 'lucide-react';
import { toast } from '@/lib/toast';
import { formatDateTimeSafe } from '@/lib/helpers';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';

import {
  useMcpToken,
  useRevokePreviousMcpToken,
  useRotateMcpToken,
  useSetMcpEnforce,
} from '../hooks/useMcpToken';
import type { McpTokenState } from '../services/mcpTokenService';

/** MCP-TOKEN-UI: the MCP server's bearer token, generated here, never typed or read back. */
function StatusBadge({ data }: { data: McpTokenState }) {
  if (data.unreadable) {
    return (
      <Badge variant="destructive" appearance="light" size="sm">
        Saved token unreadable, rotate it
      </Badge>
    );
  }
  return data.configured ? (
    <Badge variant="success" appearance="light" size="sm">
      Set
    </Badge>
  ) : (
    <Badge variant="secondary" appearance="light" size="sm">
      Not set
    </Badge>
  );
}

function NewToken({ token, onHide }: { token: string; onHide: () => void }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(token);
      toast.success('MCP token copied');
    } catch {
      toast.error('Could not copy the token');
    }
  };
  return (
    <div className="space-y-1.5" role="status">
      <Label htmlFor="mcp-token-new">New token, shown once</Label>
      <div className="flex items-center gap-2">
        <Input
          id="mcp-token-new"
          value={token}
          readOnly
          aria-label="New MCP token"
          className="font-mono text-xs"
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          mode="icon"
          onClick={copy}
          aria-label="Copy MCP token"
          title="Copy MCP token"
        >
          <CopyIcon className="size-4" />
        </Button>
      </div>
      <Button type="button" variant="ghost" size="sm" onClick={onHide}>
        Hide token
      </Button>
    </div>
  );
}

export default function McpTokenCard() {
  const query = useMcpToken();
  const rotate = useRotateMcpToken();
  const enforce = useSetMcpEnforce();
  const revoke = useRevokePreviousMcpToken();
  // The only place the plain token lives in the browser; gone on Hide or on leaving the page.
  const [newToken, setNewToken] = useState<string | null>(null);

  if (query.isLoading) {
    return (
      <Skeleton className="h-48 w-full" aria-label="Loading the MCP token" />
    );
  }
  if (query.isError || !query.data) {
    return (
      <Card>
        <CardContent className="py-8 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {query.error instanceof Error
              ? query.error.message
              : 'The MCP token could not be loaded.'}
          </p>
          <Button
            variant="outline"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const data = query.data;
  const busy = rotate.isPending || enforce.isPending || revoke.isPending;
  const generateLabel = data.configured ? 'Rotate token' : 'Generate token';

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>MCP access token</CardTitle>
      </CardHeader>
      <CardContent className="py-8">
        <div className="space-y-6 lg:max-w-[640px] mx-auto">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <Label>Token</Label>
              <StatusBadge data={data} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span
                className="font-mono text-sm truncate"
                title={data.masked ?? undefined}
              >
                {data.masked ?? '-'}
              </span>
              <Button
                type="button"
                variant={data.configured ? 'outline' : 'primary'}
                disabled={busy}
                onClick={() =>
                  rotate.mutate(undefined, {
                    onSuccess: (r) => setNewToken(r.token),
                  })
                }
              >
                {rotate.isPending && (
                  <LoaderCircleIcon className="size-4 animate-spin mr-2" />
                )}
                {generateLabel}
              </Button>
            </div>
            {data.rotated_at && (
              <p className="text-sm text-muted-foreground">
                Last generated {formatDateTimeSafe(data.rotated_at)}
              </p>
            )}
          </div>

          {newToken && (
            <NewToken token={newToken} onHide={() => setNewToken(null)} />
          )}

          {data.previous_valid_until && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                Previous token valid until{' '}
                {formatDateTimeSafe(data.previous_valid_until)}
              </p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => revoke.mutate(undefined)}
              >
                Revoke previous now
              </Button>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Label htmlFor="mcp-token-enforce">Enforce</Label>
            <Switch
              id="mcp-token-enforce"
              aria-label="Enforce"
              checked={data.enforce}
              disabled={!data.configured || busy}
              onCheckedChange={(v) => enforce.mutate(v)}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
