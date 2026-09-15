'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import OrderableList from '@/components/common/OrderableList';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useChatbotDomainsQuery } from '@/app/(protected)/system-management/chatbot-domains/hooks/useChatbotDomains';
import {
  useChatbotDefaultLadder,
  useSaveChatbotDefaultLadder,
} from '../hooks/useChatbotConfigMock';

/**
 * Settings > Chatbot > Cross-domain ladder card (S1, AC-1513, M5).
 *
 * The default (stock) ladder: when a stock answer is zero or short, climb in this
 * order (contract line 3). This is a shortcut onto the "inventory" domain row's own
 * `ladder` column - the same field the Domain modal's Ladder tab edits - not a
 * second setting; mocked here as its own array for Phase 1 (see the service header).
 */
export default function CrossDomainLadderCard() {
  const query = useChatbotDefaultLadder();
  const save = useSaveChatbotDefaultLadder();
  const [draft, setDraft] = useState<string[] | null>(null);
  const { data: domains } = useChatbotDomainsQuery();

  useEffect(() => {
    if (query.data && draft === null) setDraft(query.data);
  }, [query.data, draft]);

  const labelByName = useMemo(
    () => new Map((domains ?? []).map((d) => [d.name, d.label])),
    [domains],
  );
  const rungOptions = useMemo(
    () =>
      (domains ?? [])
        .filter((d) => !(draft ?? []).includes(d.name))
        .map((d) => ({ value: d.name, label: d.label })),
    [domains, draft],
  );

  if (query.isError && !draft) {
    return (
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Cross-domain ladder</CardTitle>
        </CardHeader>
        <CardContent className="py-5">
          <p className="text-sm text-destructive">
            The ladder could not be loaded. Reload the page to try again.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (query.isLoading || !draft) {
    return <Skeleton className="h-56 w-full" />;
  }

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Cross-domain ladder</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 py-5">
        <p className="text-sm text-muted-foreground">
          When a stock answer is 0 or short, climb in this order:
        </p>
        <OrderableList
          items={draft}
          labelFor={(name) => labelByName.get(name) ?? name}
          onChange={setDraft}
          onRemove={(name) => setDraft(draft.filter((n) => n !== name))}
        />
        <SearchableSelect
          value=""
          onChange={(v) => {
            if (!v || draft.includes(v)) return;
            setDraft([...draft, v]);
          }}
          placeholder="Add a rung..."
          triggerClassName="max-w-56"
          options={rungOptions}
          emptyMessage="No other domain to add."
        />
        <div className="flex justify-end">
          <Button
            type="button"
            size="sm"
            disabled={save.isPending}
            onClick={() => draft && save.mutate(draft, { onSuccess: (saved) => setDraft(saved) })}
          >
            {save.isPending && <LoaderCircleIcon className="size-4 animate-spin" />}
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
