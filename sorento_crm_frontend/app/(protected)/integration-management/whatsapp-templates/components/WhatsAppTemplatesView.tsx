'use client';

import { useCallback, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquareText, RefreshCw } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { syncTemplates } from '@/services/whatsappTemplateService';
import TemplateDefaultsSection from './TemplateDefaultsSection';
import TemplatesGrid from './TemplatesGrid';

export default function WhatsAppTemplatesView() {
  const queryClient = useQueryClient();
  const [isSyncing, setIsSyncing] = useState(false);

  // PHASE 1 MOCK - workspace/channel card data comes from the templates sync
  // endpoints in Phase 2 (respond_workspaces + respond_channels).
  const workspace = {
    name: 'Sorento',
    space_id: '143179',
    channel_name: 'Sorento WhatsApp',
    channel_type: 'WhatsApp Cloud API',
  };

  const handleSync = useCallback(async () => {
    setIsSyncing(true);
    try {
      const result = await syncTemplates();
      toast.success(
        `Templates synced: ${result.synced} updated, ${result.deleted} removed (${result.channels} channel${result.channels === 1 ? '' : 's'})`,
      );
      await queryClient.invalidateQueries({ queryKey: ['whatsapp-templates'] });
      await queryClient.invalidateQueries({ queryKey: ['whatsapp-template-defaults'] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Template sync failed');
    } finally {
      setIsSyncing(false);
    }
  }, [queryClient]);

  const { data: syncMeta } = useQuery({
    queryKey: ['whatsapp-templates', 'meta'],
    queryFn: async () => ({ last_synced_at: new Date().toISOString() }),
  });

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <CardTitle className="flex items-center gap-2 text-base">
            <MessageSquareText className="size-4 text-muted-foreground" />
            Respond.io Workspace
          </CardTitle>
          <Button onClick={handleSync} disabled={isSyncing} size="sm">
            <RefreshCw className={`size-4 me-2 ${isSyncing ? 'animate-spin' : ''}`} />
            {isSyncing ? 'Syncing…' : 'Sync templates'}
          </Button>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
            <div>
              <span className="text-muted-foreground me-2">Workspace:</span>
              <span className="font-medium">{workspace.name}</span>
              <span className="text-muted-foreground ms-1">({workspace.space_id})</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Channel:</span>
              <span className="font-medium">{workspace.channel_name}</span>
              <Badge variant="secondary">
                {workspace.channel_type}
              </Badge>
            </div>
            {syncMeta?.last_synced_at && (
              <div className="text-muted-foreground text-xs">
                Templates are synced daily; use the button after editing templates in Meta.
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <TemplateDefaultsSection />

      <TemplatesGrid />
    </div>
  );
}
