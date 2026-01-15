'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useConversationSLATrackingDetail } from '../hooks/useConversationSLATracking';
import { formatDate, formatDateTime, formatDuration } from '@/lib/helpers';
import EscalationLogTable from './EscalationLogTable';
import { CheckCircle, Clock, AlertCircle, RefreshCw } from 'lucide-react';

interface ConversationSLATrackingDetailProps {
  trackingId: string;
}

export default function ConversationSLATrackingDetail({ trackingId }: ConversationSLATrackingDetailProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: tracking, isLoading } = useConversationSLATrackingDetail(trackingId);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking-detail', trackingId] });
    setIsRefreshing(false);
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!tracking) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Conversation SLA tracking not found</p>
        <Button variant="outline" onClick={() => router.push('/sla-management/conversation-sla-tracking')} className="mt-4">
          Back to Conversation SLA Tracking
        </Button>
      </div>
    );
  }

  const getTimeInCurrentTier = () => {
    const now = new Date();
    const started = new Date(tracking.current_tier_started_at);
    const diff = now.getTime() - started.getTime();
    return formatDuration(diff);
  };

  const getTimeToResolution = () => {
    if (tracking.is_resolved && tracking.resolved_at) {
      const initiated = new Date(tracking.initiated_at);
      const resolved = new Date(tracking.resolved_at);
      const diff = resolved.getTime() - initiated.getTime();
      return formatDuration(diff);
    }
    return null;
  };

  const getTimeRemaining = () => {
    if (tracking.is_resolved) return null;
    const now = new Date();
    const due = new Date(tracking.due_at);
    const diff = due.getTime() - now.getTime();
    return formatDuration(diff);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Contact: {tracking.respond_contact_id}</h1>
            {tracking.is_resolved ? (
              <Badge variant="success" appearance="ghost">
                <CheckCircle className="size-3 mr-1" />
                Resolved
              </Badge>
            ) : tracking.escalated_at ? (
              <Badge variant="warning" appearance="ghost">
                <AlertCircle className="size-3 mr-1" />
                Escalated
              </Badge>
            ) : (
              <Badge variant="info" appearance="ghost">
                <Clock className="size-3 mr-1" />
                Pending
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Policy: {tracking.policy_name || tracking.policy_code} • Current Tier: {tracking.current_tier}
          </p>
        </div>
        <Button
          variant="outline"
          onClick={handleRefresh}
          disabled={isRefreshing || isLoading}
        >
          <RefreshCw className={`size-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="escalation-log">Escalation Log</TabsTrigger>
        </TabsList>

        {/* Tab 1: Overview */}
        <TabsContent value="overview">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Key Metrics Cards */}
            <Card>
              <CardHeader>
                <CardTitle>Key Metrics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">Time in Current Tier</p>
                  <p className="font-medium text-lg">{getTimeInCurrentTier()}</p>
                </div>
                {getTimeToResolution() !== null && (
                  <div>
                    <p className="text-sm text-muted-foreground">Time to Resolution</p>
                    <p className="font-medium text-lg text-green-600">{getTimeToResolution()}</p>
                  </div>
                )}
                {getTimeRemaining() !== null && (
                  <div>
                    <p className="text-sm text-muted-foreground">Time Remaining</p>
                    <p className={`font-medium text-lg ${getTimeRemaining()!.startsWith('-') ? 'text-destructive' : ''}`}>
                      {getTimeRemaining()!.startsWith('-') ? `${getTimeRemaining()!.substring(1)} overdue` : `${getTimeRemaining()} left`}
                    </p>
                  </div>
                )}
                {tracking.resolution_duration && (
                  <div>
                    <p className="text-sm text-muted-foreground">Resolution Duration</p>
                    <p className="font-medium text-lg">{formatDuration(tracking.resolution_duration * 3600 * 1000)}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Timeline Visualization */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Tier Progression Timeline</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {(() => {
                    // Build timeline items from escalation logs and current tier
                    const timelineItems: Array<{
                      tier: number;
                      startedAt: Date;
                      isEscalation: boolean;
                      reason?: string;
                      isCurrent: boolean;
                    }> = [];
                    
                    // Determine initial tier
                    const initialTier = tracking.escalation_logs && tracking.escalation_logs.length > 0
                      ? tracking.escalation_logs[0].from_tier
                      : tracking.current_tier;
                    
                    // Check if current tier matches the last escalation log
                    const lastLog = tracking.escalation_logs && tracking.escalation_logs.length > 0
                      ? tracking.escalation_logs[tracking.escalation_logs.length - 1]
                      : null;
                    const isCurrentTierInLogs = lastLog && lastLog.to_tier === tracking.current_tier;
                    
                    // Add initial tier (only if there are escalation logs, otherwise it's handled below)
                    if (tracking.escalation_logs && tracking.escalation_logs.length > 0) {
                      timelineItems.push({
                        tier: initialTier,
                        startedAt: new Date(tracking.initiated_at),
                        isEscalation: false,
                        isCurrent: false,
                      });
                    }
                    
                    // Add escalation logs
                    if (tracking.escalation_logs && tracking.escalation_logs.length > 0) {
                      tracking.escalation_logs.forEach((log, index) => {
                        const isLast = index === tracking.escalation_logs!.length - 1;
                        timelineItems.push({
                          tier: log.to_tier,
                          startedAt: new Date(log.escalated_at),
                          isEscalation: log.from_tier !== log.to_tier,
                          reason: log.reason,
                          isCurrent: isLast && log.to_tier === tracking.current_tier,
                        });
                      });
                    } else {
                      // If no escalation logs, show current tier as initial tier
                      timelineItems.push({
                        tier: tracking.current_tier,
                        startedAt: new Date(tracking.current_tier_started_at),
                        isEscalation: false,
                        isCurrent: true,
                      });
                    }
                    
                    return timelineItems.map((item, index) => (
                      <div key={index} className="flex items-center gap-4">
                        <div className="flex flex-col items-center">
                          <div className={`size-8 rounded-full flex items-center justify-center text-white font-bold ${
                            item.isCurrent 
                              ? 'bg-primary' 
                              : item.isEscalation 
                                ? 'bg-orange-500' 
                                : 'bg-blue-500'
                          }`}>
                            {item.tier}
                          </div>
                          {index < timelineItems.length - 1 && (
                            <div className="h-12 w-0.5 bg-border mt-2"></div>
                          )}
                        </div>
                        <div className="flex-1">
                          <p className="font-medium">
                            {item.isEscalation 
                              ? `Escalated to Tier ${item.tier}${item.isCurrent ? ' (Current)' : ''}` 
                              : `Tier ${item.tier}${item.isCurrent ? ' (Current)' : ''}`
                            }
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {item.isEscalation ? 'Escalated' : 'Started'}: {formatDateTime(item.startedAt)}
                          </p>
                          {item.reason && (
                            <p className="text-sm text-muted-foreground">Reason: {item.reason}</p>
                          )}
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Detailed Information */}
          <Card>
            <CardHeader>
              <CardTitle>Tracking Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Respond Contact ID</p>
                  <p className="font-medium">{tracking.respond_contact_id}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Policy</p>
                  <p className="font-medium">{tracking.policy_name || tracking.policy_code}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Current Tier</p>
                  <p className="font-medium">Tier {tracking.current_tier}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Assigned To</p>
                  <p className="font-medium">{tracking.assigned_to || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Initiated At</p>
                  <p className="font-medium">{formatDateTime(new Date(tracking.initiated_at))}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Current Tier Started At</p>
                  <p className="font-medium">{formatDateTime(new Date(tracking.current_tier_started_at))}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Due At</p>
                  <p className="font-medium">{formatDateTime(new Date(tracking.due_at))}</p>
                </div>
                {tracking.escalated_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Escalated At</p>
                    <p className="font-medium">{formatDateTime(new Date(tracking.escalated_at))}</p>
                  </div>
                )}
                {tracking.escalation_reason && (
                  <div className="md:col-span-2">
                    <p className="text-sm text-muted-foreground">Escalation Reason</p>
                    <p className="font-medium">{tracking.escalation_reason}</p>
                  </div>
                )}
                {tracking.is_resolved && tracking.resolved_at && (
                  <>
                    <div>
                      <p className="text-sm text-muted-foreground">Resolved At</p>
                      <p className="font-medium">{formatDateTime(new Date(tracking.resolved_at))}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Resolved By</p>
                      <p className="font-medium">{tracking.resolved_by || '-'}</p>
                    </div>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Escalation Log */}
        <TabsContent value="escalation-log">
          <EscalationLogTable trackingId={trackingId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
