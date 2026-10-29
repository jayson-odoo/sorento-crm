'use client';

import { useState } from 'react';
import { Loader2, Plus, SendHorizonal } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { getRespondContactsOutbound } from '../../respond-contacts/services/respondContactOutboundService';
import { useAgentConsole } from '../hooks/useAgentConsole';
import {
  AGENT_LIMIT_LABELS,
  agentToolLabel,
  type AgentReplyMeta,
} from '../types/agentConsole.types';

async function fetchContactOptions(query: string): Promise<SearchableSelectOption[]> {
  const result = await getRespondContactsOutbound({ pageIndex: 0, pageSize: 20, searchQuery: query });
  return result.data
    .filter((row) => Boolean(row.respond_io_id))
    .map((row) => ({
      value: row.respond_io_id as string,
      label: row.name || row.phone_number || (row.respond_io_id as string),
      description: row.name && row.phone_number ? row.phone_number : undefined,
    }));
}

function Bubble({ role, children }: { role: 'user' | 'agent'; children: React.ReactNode }) {
  const isUser = role === 'user';
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-3 py-2.5 text-sm leading-relaxed shadow-sm',
          isUser ? 'bg-primary/15 text-foreground' : 'bg-muted text-foreground',
        )}
      >
        {children}
      </div>
    </div>
  );
}

function ReplyMeta({ meta }: { meta: AgentReplyMeta }) {
  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground"
      data-testid="agent-reply-meta"
    >
      <span>{meta.rounds === 1 ? '1 round' : `${meta.rounds} rounds`}</span>
      {meta.tool_calls.map((call, index) => (
        <Badge key={`${call.name}-${index}`} variant="secondary" size="sm">
          {agentToolLabel(call.name)}: {call.status}
        </Badge>
      ))}
      {meta.limit_hit ? (
        <span>Stopped: {AGENT_LIMIT_LABELS[meta.limit_hit] ?? meta.limit_hit}</span>
      ) : null}
    </div>
  );
}

export default function AgentConsole() {
  const agent = useAgentConsole();
  const [draft, setDraft] = useState('');

  const submit = () => {
    const text = draft.trim();
    if (!text || agent.sending || !agent.contactId) return;
    setDraft('');
    agent.send(text);
  };

  return (
    <div className="flex min-h-[70dvh] flex-col gap-3 lg:h-[calc(100dvh-16rem)]" data-testid="agent-console">
      <div className="flex flex-wrap items-end gap-3 border-b pb-3">
        <div className="min-w-[220px] flex-1 sm:flex-none">
          <Label className="mb-1 block text-xs text-muted-foreground">Contact</Label>
          <SearchableSelect
            value={agent.contactId ?? ''}
            onChange={() => {
              /* handled via onOptionChange, which also carries the label */
            }}
            onOptionChange={(option) => {
              if (option) agent.setContact(option.value, option.label);
            }}
            fetchOptions={fetchContactOptions}
            selectedOption={
              agent.contactId ? { value: agent.contactId, label: agent.contactLabel } : undefined
            }
            placeholder="Pick a contact..."
            size="sm"
          />
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={!agent.contactId || agent.startingNew || agent.sending}
          onClick={agent.startNew}
        >
          <Plus className="size-3.5" />
          New conversation
        </Button>
      </div>

      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pr-1"
        data-testid="agent-console-thread"
      >
        {agent.turns.map((turn) => (
          <div key={turn.turn_id} className="space-y-3">
            <Bubble role="user">
              <p className="whitespace-pre-wrap break-words">{turn.text}</p>
            </Bubble>
            {turn.reply_text ? (
              <Bubble role="agent">
                <p className="whitespace-pre-wrap break-words">{turn.reply_text}</p>
                {agent.metaByTurn[turn.turn_id] ? (
                  <ReplyMeta meta={agent.metaByTurn[turn.turn_id]} />
                ) : null}
              </Bubble>
            ) : null}
          </div>
        ))}
        {agent.pendingText ? (
          <>
            <Bubble role="user">
              <p className="whitespace-pre-wrap break-words">{agent.pendingText}</p>
            </Bubble>
            <Bubble role="agent">
              <p className="flex items-center gap-1.5 italic text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                Working...
              </p>
            </Bubble>
          </>
        ) : null}
        {agent.notice ? (
          <p role="alert" className="text-sm text-destructive">
            {agent.notice}
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
          disabled={agent.sending || !agent.contactId}
          className="min-w-0 flex-1 resize-none"
          aria-label="Message"
        />
        <Button
          type="button"
          size="icon"
          aria-label="Send"
          disabled={agent.sending || !agent.contactId || !draft.trim()}
          onClick={submit}
        >
          <SendHorizonal className="size-4" />
        </Button>
      </div>
    </div>
  );
}
