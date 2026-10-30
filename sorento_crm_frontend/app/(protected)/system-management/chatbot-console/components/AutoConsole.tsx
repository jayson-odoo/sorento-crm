'use client';

import { useState } from 'react';
import { Loader2, SendHorizonal } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { WhatsAppText } from '@/components/chatbot/WhatsAppText';
import { useAutoConsole } from '../hooks/useAutoConsole';
import { AUTO_REASON_LABELS } from '../types/agentConsole.types';
import {
  ActionOutcome,
  Bubble,
  ProposalActions,
  ReplyMeta,
  StepsDisclosure,
  fetchContactOptions,
} from './AgentReplyParts';

export default function AutoConsole() {
  const auto = useAutoConsole();
  const [draft, setDraft] = useState('');

  const submit = () => {
    const text = draft.trim();
    if (!text || auto.sending || !auto.contactId) return;
    setDraft('');
    auto.send(text);
  };

  return (
    <div className="flex min-h-[70dvh] flex-col gap-3 lg:h-[calc(100dvh-16rem)]" data-testid="auto-console">
      <div className="border-b pb-3">
        <div className="min-w-[220px] sm:max-w-sm">
          <Label className="mb-1 block text-xs text-muted-foreground">Contact</Label>
          <SearchableSelect
            value={auto.contactId ?? ''}
            onChange={() => {
              /* handled via onOptionChange, which also carries the label */
            }}
            onOptionChange={(option) => {
              if (option) auto.setContact(option.value, option.label);
            }}
            fetchOptions={fetchContactOptions}
            selectedOption={
              auto.contactId ? { value: auto.contactId, label: auto.contactLabel } : undefined
            }
            placeholder="Pick a contact..."
            size="sm"
          />
        </div>
      </div>

      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pr-1"
        data-testid="auto-console-thread"
      >
        {auto.contactId && auto.entries.length === 0 && !auto.pendingText ? (
          <div className="py-10 text-center">
            <p className="text-sm font-medium">No messages yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Each message goes to the bot or the agent, whichever fits it.
            </p>
          </div>
        ) : null}
        {auto.entries.map((entry) => {
          const reason = AUTO_REASON_LABELS[entry.route.reason];
          const outcome = auto.outcomeByEntry[entry.id];
          return (
            <div key={entry.id} className="space-y-3">
              <Bubble role="user">
                <p className="whitespace-pre-wrap break-words">{entry.text}</p>
              </Bubble>
              <Bubble role="agent">
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge
                    variant={entry.route.route === 'agent' ? 'primary' : 'secondary'}
                    appearance="light"
                    size="sm"
                    data-testid="auto-route-badge"
                  >
                    {entry.route.route === 'agent' ? 'Agent' : 'Bot'}
                  </Badge>
                  {reason ? (
                    <span className="text-xs text-muted-foreground" data-testid="auto-route-reason">
                      {reason}
                    </span>
                  ) : null}
                </div>
                <p className="whitespace-pre-wrap break-words">
                  <WhatsAppText text={entry.reply} />
                </p>
                {entry.extraMessages.map((message, index) => (
                  <p key={index} className="mt-1.5 whitespace-pre-wrap break-words">
                    <WhatsAppText text={message} />
                  </p>
                ))}
                {entry.meta ? <ReplyMeta meta={entry.meta} /> : null}
                {entry.steps ? <StepsDisclosure steps={entry.steps} /> : null}
                {entry.pendingAction && !outcome ? (
                  <ProposalActions
                    action={entry.pendingAction}
                    busy={auto.deciding}
                    showLines
                    onConfirm={() => auto.confirmAction(entry.pendingAction!.id, entry.id)}
                    onCancel={() => auto.cancelAction(entry.pendingAction!.id, entry.id)}
                  />
                ) : null}
              </Bubble>
              {outcome ? <ActionOutcome outcome={outcome} /> : null}
            </div>
          );
        })}
        {auto.pendingText ? (
          <>
            <Bubble role="user">
              <p className="whitespace-pre-wrap break-words">{auto.pendingText}</p>
            </Bubble>
            <Bubble role="agent">
              <p className="flex items-center gap-1.5 italic text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                Working...
              </p>
            </Bubble>
          </>
        ) : null}
        {auto.notice ? (
          <p role="alert" className="text-sm text-destructive">
            {auto.notice}
          </p>
        ) : null}
      </div>

      <div className="flex items-end gap-2 border-t pt-3">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about stock, orders or sales"
          rows={2}
          disabled={auto.sending || !auto.contactId}
          className="min-w-0 flex-1 resize-none"
          aria-label="Message"
        />
        <Button
          type="button"
          size="icon"
          aria-label="Send"
          disabled={auto.sending || !auto.contactId || !draft.trim()}
          onClick={submit}
        >
          <SendHorizonal className="size-4" />
        </Button>
      </div>
    </div>
  );
}
