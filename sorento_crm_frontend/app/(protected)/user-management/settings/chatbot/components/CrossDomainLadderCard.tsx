'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import OrderableList from '@/components/common/OrderableList';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useChatbotDomainsQuery,
  useUpdateChatbotDomain,
} from '@/app/(protected)/system-management/chatbot-domains/hooks/useChatbotDomains';
import type { ChatbotDomainInput } from '@/app/(protected)/system-management/chatbot-domains/types/chatbotDomain.types';

/** The domain the default (stock) ladder climbs from - contract line 3. */
const DEFAULT_LADDER_DOMAIN = 'inventory';

/**
 * Settings > Chatbot > Cross-domain ladder card (chatbot turn re-architecture, AC-1513, M5).
 *
 * The default (stock) ladder: when a stock answer is zero or short, climb in this
 * order. A shortcut onto the "inventory" domain row's own `ladder` column - the SAME
 * field the Domain modal's Ladder tab edits (S5, AC-1561) - not a second setting; saved
 * through `chatbotDomainService` rather than duplicating the column.
 */
export default function CrossDomainLadderCard() {
  const { data: domains, isLoading, isError } = useChatbotDomainsQuery();
  const update = useUpdateChatbotDomain();
  const [draft, setDraft] = useState<string[] | null>(null);

  const inventoryDomain = useMemo(
    () => (domains ?? []).find((d) => d.name === DEFAULT_LADDER_DOMAIN),
    [domains],
  );

  useEffect(() => {
    if (inventoryDomain && draft === null) setDraft(inventoryDomain.ladder);
  }, [inventoryDomain, draft]);

  const labelByName = useMemo(
    () => new Map((domains ?? []).map((d) => [d.name, d.label])),
    [domains],
  );
  const rungOptions = useMemo(
    () =>
      (domains ?? [])
        .filter((d) => d.name !== DEFAULT_LADDER_DOMAIN && !(draft ?? []).includes(d.name))
        .map((d) => ({ value: d.name, label: d.label })),
    [domains, draft],
  );

  if (isError && !draft) {
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

  if (isLoading || !draft || !inventoryDomain) {
    return <Skeleton className="h-56 w-full" />;
  }

  const save = () => {
    if (!draft) return;
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- stripped, not sent
    const { id, updated_at, ...rest } = inventoryDomain;
    const input: ChatbotDomainInput = { ...rest, ladder: draft };
    update.mutate(
      { id: inventoryDomain.id, input },
      { onSuccess: (saved) => setDraft(saved.ladder) },
    );
  };

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
          <Button type="button" size="sm" disabled={update.isPending} onClick={save}>
            {update.isPending && <LoaderCircleIcon className="size-4 animate-spin" />}
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
