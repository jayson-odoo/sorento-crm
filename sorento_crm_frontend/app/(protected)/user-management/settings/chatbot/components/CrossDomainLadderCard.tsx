'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import OrderableList from '@/components/common/OrderableList';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { ChatbotDomain } from '@/app/(protected)/system-management/chatbot-domains/types/chatbotDomain.types';

/** The domain the default (stock) ladder climbs from - contract line 3. */
export const DEFAULT_LADDER_DOMAIN = 'inventory';

/**
 * Settings > Chatbot > Cross-domain ladder card (chatbot turn re-architecture, AC-1513, M5).
 *
 * The default (stock) ladder: when a stock answer is zero or short, climb in this
 * order. A shortcut onto the "inventory" domain row's own `ladder` column - the SAME
 * field the Domain modal's Ladder tab edits (S5, AC-1561) - not a second setting; saved
 * through `chatbotDomainService` rather than duplicating the column.
 *
 * CONTROLLED, and with no Save of its own: the page owns the draft and the ONE Save
 * button, same as the Memory and Tier order cards (browser pass 2, step 4 - a second
 * Save on the page is a second answer to "did that save?").
 */
export default function CrossDomainLadderCard({
  value,
  onChange,
  domains,
  isLoading,
  isError,
}: {
  value: string[] | null;
  onChange: (next: string[]) => void;
  domains: ChatbotDomain[] | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  const draft = value;

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

  if (isLoading || !draft) {
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
          onChange={onChange}
          onRemove={(name) => onChange(draft.filter((n) => n !== name))}
        />
        <SearchableSelect
          value=""
          onChange={(v) => {
            if (!v || draft.includes(v)) return;
            onChange([...draft, v]);
          }}
          placeholder="Add a rung..."
          triggerClassName="max-w-56"
          options={rungOptions}
          emptyMessage="No other domain to add."
        />
      </CardContent>
    </Card>
  );
}
