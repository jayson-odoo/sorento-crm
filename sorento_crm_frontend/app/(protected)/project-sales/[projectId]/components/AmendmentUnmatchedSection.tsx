'use client';

import { HelpCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { AmendmentUnmatched } from '../../_shared/types/projectSalesOrder.types';

/**
 * Rows that could not be matched between the two versions.
 *
 * This section renders whether or not there is anything in it. A delta that quietly drops a
 * phase it could not pair up is a delta that lies, and the reviewer has no way of knowing.
 */
export function AmendmentUnmatchedSection({ unmatched }: { unmatched: AmendmentUnmatched[] }) {
  return (
    <Card className={unmatched.length > 0 ? 'border-amber-300 dark:border-amber-800' : undefined}>
      <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
          <HelpCircle className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="break-words">Could not be matched</span>
        </CardTitle>
        {unmatched.length > 0 && (
          <Badge variant="warning" appearance="light">
            {`${unmatched.length} to confirm`}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-2">
        {unmatched.length === 0 ? (
          <p
            className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground"
            data-testid="unmatched-empty"
          >
            Every phase and product matched across the two versions.
          </p>
        ) : (
          unmatched.map((entry, index) => (
            <div
              key={`${entry.reason}-${index}`}
              className="rounded-lg border border-border px-3 py-2.5"
            >
              <p className="break-words text-sm font-medium">{entry.reason}</p>
              {entry.detail && (
                <p className="mt-0.5 break-words text-sm text-muted-foreground">{entry.detail}</p>
              )}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
