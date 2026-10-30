'use client';

import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { ConsoleRoute } from '../types/chatbotConsole.types';

/** Plain words for the router's reason codes; `router_failed:*` and `not_eligible:*` carry a detail after the colon. */
const REASON_WORDS: Record<string, string> = {
  classified: 'Classified',
  low_confidence: 'Low confidence',
  open_question: 'Open question',
  media: 'Media',
  daily_cap: 'Daily cap',
  pending_action: 'Pending action',
  router_failed: 'Router failed',
  not_eligible: 'Not eligible',
};

export function routeReasonWords(reason: string): string {
  const key = reason.split(':')[0];
  return REASON_WORDS[key] ?? key.replace(/_/g, ' ');
}

/** Which side answered, as a pill under the answer; opening it shows why. */
export function RoutePill({ route }: { route: ConsoleRoute }) {
  const isAgent = route.side === 'agent';
  const rows: [string, string][] = [
    ['Reason', routeReasonWords(route.reason)],
    ['Score', route.score == null ? '-' : route.score.toFixed(2)],
    ['Model', route.model || '-'],
    ['Time', route.ms == null ? '-' : `${route.ms} ms`],
  ];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="rounded-full focus-visible:ring-2 focus-visible:ring-ring">
          <Badge variant={isAgent ? 'primary' : 'secondary'} appearance="light" size="sm">
            {isAgent ? 'Agent' : 'Chat'}
          </Badge>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-4" align="start">
        <dl className="space-y-2 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="truncate text-foreground" title={value}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </PopoverContent>
    </Popover>
  );
}
