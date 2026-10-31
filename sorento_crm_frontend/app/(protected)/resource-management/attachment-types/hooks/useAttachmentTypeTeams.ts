import { useEffect, useState } from 'react';
import { getTeams } from '@/app/(protected)/user-management/teams/services/teamService';

interface TeamOption {
  id: string;
  name: string;
}

/**
 * Teams for the "Escalate to" select on the attachment type form. A plain effect rather than a
 * query so the form still renders where no QueryClientProvider is mounted; a failed load leaves
 * the list empty and the select simply has nothing to offer.
 */
export function useAttachmentTypeTeams(enabled: boolean = true) {
  const [data, setData] = useState<TeamOption[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    getTeams()
      .then((teams) => {
        if (!cancelled) setData(teams.map((t) => ({ id: String(t.id), name: t.name })));
      })
      .catch(() => {
        if (!cancelled) setData([]);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { data };
}
