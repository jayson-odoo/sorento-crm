'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useNoToolAsks } from '../hooks/useAIUsage';
import type { NoToolAsk } from '../services/aiUsageService';

const CHANNEL_LABELS: Record<string, string> = {
  panel: 'Side panel',
  whatsapp: 'WhatsApp',
  console: 'Console',
};

export function channelLabel(channel: string | null): string {
  if (!channel) return '-';
  return CHANNEL_LABELS[channel] ?? channel;
}

function formatAskedAt(d: string): string {
  try {
    return formatDateTimeInMalaysia(d);
  } catch {
    return d;
  }
}

export function NoToolAsksTable({ items }: { items: NoToolAsk[] }) {
  if (items.length === 0) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm font-medium">No asks without a tool</p>
        <p className="text-sm text-muted-foreground">
          Nothing in the last 30 days.
        </p>
      </div>
    );
  }
  return (
    <ScrollArea>
      <table className="w-auto min-w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="py-2 text-left font-medium">Ask</th>
            <th className="py-2 text-left font-medium">Date</th>
            <th className="py-2 text-left font-medium">Area</th>
            <th className="py-2 text-left font-medium">User</th>
            <th className="py-2 text-left font-medium">Channel</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, idx) => (
            <tr
              key={`${it.turn_id}-${idx}`}
              className="border-b align-top last:border-0"
            >
              <td
                className="max-w-[28rem] min-w-[9rem] py-2 pe-3"
                title={it.ask}
              >
                {it.ask}
              </td>
              <td className="py-2 pe-3 text-xs whitespace-nowrap text-muted-foreground">
                {formatAskedAt(it.asked_at)}
              </td>
              <td className="py-2 pe-3">
                {it.area ? (
                  <Badge variant="secondary" className="text-xs">
                    {it.area}
                  </Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">-</span>
                )}
              </td>
              <td className="py-2 pe-3">
                {it.who || <span className="text-muted-foreground">-</span>}
              </td>
              <td className="py-2">
                <Badge variant="outline" className="text-xs">
                  {channelLabel(it.channel)}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
}

export function NoToolAsksCard() {
  const query = useNoToolAsks();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Asks with no tool (last 30 days)</CardTitle>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <SectionSkeleton rows={3} />
        ) : query.isError ? (
          <p className="text-sm text-destructive">
            {(query.error as Error)?.message ||
              'Failed to load the asks with no tool.'}
          </p>
        ) : (
          <NoToolAsksTable items={query.data || []} />
        )}
      </CardContent>
    </Card>
  );
}
