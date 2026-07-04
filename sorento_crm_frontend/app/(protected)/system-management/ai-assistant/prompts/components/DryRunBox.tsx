'use client';

import { useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { useDryRun } from '../../hooks/useAIAssistantPrompts';

/**
 * Single-message dry-run (PLAN §9b Q5). Runs one real assistant turn with ONLY
 * this key overridden to the selected version. Disabled for dormant keys.
 */
export function DryRunBox({
  keyName,
  versionId,
  versionLabel,
  disabled,
  disabledReason,
}: {
  keyName: string;
  versionId: string | null;
  versionLabel: string;
  disabled: boolean;
  disabledReason?: string;
}) {
  const [message, setMessage] = useState('');
  const dryRun = useDryRun(keyName);

  const run = () => {
    if (!versionId || !message.trim()) return;
    dryRun.mutate({ message: message.trim(), version_id: versionId });
  };

  return (
    <div className="space-y-3 rounded-md border p-3" data-testid="dry-run-box">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Test this version</p>
        <span className="text-xs text-muted-foreground">{versionLabel}</span>
      </div>
      {disabled ? (
        <p className="text-xs text-muted-foreground" data-testid="dry-run-disabled">
          {disabledReason || 'Dry-run is disabled for this prompt.'}
        </p>
      ) : (
        <>
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type one message to run through the assistant with this version swapped in…"
            className="min-h-20 text-sm"
            data-testid="dry-run-input"
          />
          <Button size="sm" onClick={run} disabled={dryRun.isPending || !message.trim() || !versionId}>
            {dryRun.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Running…
              </>
            ) : (
              <>
                <Play className="size-4" /> Run
              </>
            )}
          </Button>
          {dryRun.isError ? (
            <p className="text-xs text-destructive" data-testid="dry-run-error">
              {(dryRun.error as Error)?.message || 'Dry-run failed'}
            </p>
          ) : null}
          {dryRun.data ? (
            <div className="space-y-2 rounded-md bg-muted/40 p-3" data-testid="dry-run-output">
              <p className="whitespace-pre-wrap text-sm">{dryRun.data.output}</p>
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <Badge variant="secondary" className="font-mono">
                  {dryRun.data.token_usage.total_tokens} tokens
                </Badge>
                {dryRun.data.tool_calls.map((t, i) => (
                  <Badge key={`${t.name}-${i}`} variant={t.ok ? 'success' : 'destructive'} className="font-mono">
                    {t.name}
                    {t.ok ? '' : ' ✕'}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
