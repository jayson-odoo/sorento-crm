'use client';

import { LoaderCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useCatalogueStatusQuery } from '../hooks/useCatalogueStatusQuery';

/**
 * One line above the registry grid: when the catalogue was last read, and
 * whether it needs reading again (AC-A.3). "Reread catalogue" itself lives in
 * the page's Actions menu (AC-A.1) - this line only reports state.
 */
export function CatalogueFreshnessLine() {
  const { data: status, isLoading, isError } = useCatalogueStatusQuery();

  if (isLoading || isError || !status) return null;

  const running = status.status === 'running';
  const stale = status.rules_changed_since_last_read;

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {/* `basis-full` at 375, `basis-0` from `sm`: a wrapping row breaks its
          lines on flex-basis, and basis 0 alone kept this line and the pill
          from ever getting their own row on a phone. */}
      <span className="min-w-0 grow basis-full text-muted-foreground sm:basis-0">
        {running ? (
          <span className="inline-flex items-center gap-1.5">
            <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
            Reading...
          </span>
        ) : !status.ever_read || !status.finished_at ? (
          'Never read'
        ) : (
          `Catalogue read ${formatDateTimeInMalaysia(status.finished_at)}`
        )}
      </span>
      {!running && stale && (
        <Badge variant="warning" appearance="light" shape="circle" size="sm">
          Rules changed since
        </Badge>
      )}
    </div>
  );
}

export default CatalogueFreshnessLine;
