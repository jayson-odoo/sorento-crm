'use client';

import { useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { TurnPanel } from '../../../chat-history/components/TurnPanel';
import { useDryRun } from '../../hooks/useAIAssistantPrompts';
import { CHATBOT_TURN_PROMPT_KEYS } from '../../services/aiPromptsService';

/**
 * Single-message dry-run (PLAN §9b Q5). Runs one real assistant turn with ONLY
 * this key overridden to the selected version. Disabled for dormant keys.
 *
 * For the two chatbot keys it runs a dry-run chatbot TURN instead (AC-807) and renders
 * the result with Chat History's own `TurnPanel`, so an operator reads one trace layout
 * wherever they meet a turn. That reuse is the reason there is no renderer here: a second
 * timeline would be the same information in a second dialect.
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
  const [contact, setContact] = useState('');
  const dryRun = useDryRun(keyName);
  const runsATurn = CHATBOT_TURN_PROMPT_KEYS.includes(keyName);
  const ready = Boolean(versionId) && Boolean(message.trim()) && (!runsATurn || Boolean(contact.trim()));

  const run = () => {
    if (!versionId || !ready) return;
    dryRun.mutate({
      message: message.trim(),
      version_id: versionId,
      ...(runsATurn ? { contact_respond_id: contact.trim() } : {}),
    });
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
          {runsATurn ? (
            <div className="grid gap-1.5">
              <Label htmlFor="dry-run-contact" className="text-xs">
                Contact
              </Label>
              <Input
                id="dry-run-contact"
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                placeholder="Respond.io contact id to run the turn against"
                className="text-sm"
                data-testid="dry-run-contact"
              />
            </div>
          ) : null}
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={
              runsATurn
                ? 'Type one message to run through the bot with this version swapped in…'
                : 'Type one message to run through the assistant with this version swapped in…'
            }
            className="min-h-20 text-sm"
            data-testid="dry-run-input"
          />
          <Button size="sm" onClick={run} disabled={dryRun.isPending || !ready}>
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
          {dryRun.data && runsATurn ? (
            <div className="space-y-2" data-testid="dry-run-turn">
              {dryRun.data.turn ? (
                <TurnPanel
                  turn={dryRun.data.turn}
                  retryUnavailableReason="This turn was a test, so there is nothing to retry."
                />
              ) : (
                <p className="text-xs text-muted-foreground">
                  The turn ran but its record could not be read back.
                </p>
              )}
            </div>
          ) : null}
          {dryRun.data && !runsATurn ? (
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
