'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useConversationSLATrackingDetail, useConversationSLATracking, useDeleteConversationSLATracking } from '../hooks/useConversationSLATracking';
import { formatDate, formatDateTime, formatDuration, formatDurationWithSeconds, parseDateTimeAsUTC } from '@/lib/helpers';
import EventLogTable from './EventLogTable';
import { CheckCircle, Clock, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import RecordNavigation from '@/components/common/RecordNavigation';

interface ConversationSLATrackingDetailProps {
  trackingId: string;
}

export default function ConversationSLATrackingDetail({ trackingId }: ConversationSLATrackingDetailProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: tracking, isLoading } = useConversationSLATrackingDetail(trackingId);
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
      assigned_to: undefined,
      policy_id: undefined,
      status: undefined,
    }),
    [],
  );
  const { data: navigationData } = useConversationSLATracking(navigationParams);
  const navigationItems = navigationData?.data ?? [];
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const deleteMutation = useDeleteConversationSLATracking();

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking-detail', trackingId] });
    setIsRefreshing(false);
  };

  const handleDelete = () => {
    deleteMutation.mutate(trackingId, {
      onSuccess: () => {
        router.push('/sla-management/conversation-sla-tracking');
      },
    });
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

  /** Time elapsed: when responded+resolved = resolution time; when only responded = response time; else = time since initiated. Always shows seconds. */
  const getTimeElapsed = (): string | null => {
    if (tracking.is_resolved && tracking.resolved_at && tracking.initiated_at) {
      const initiated = parseDateTimeAsUTC(tracking.initiated_at);
      const resolved = parseDateTimeAsUTC(tracking.resolved_at);
      return formatDurationWithSeconds(resolved.getTime() - initiated.getTime());
    }
    if (tracking.is_responded && tracking.responded_at && tracking.initiated_at) {
      const initiated = parseDateTimeAsUTC(tracking.initiated_at);
      const responded = parseDateTimeAsUTC(tracking.responded_at);
      return formatDurationWithSeconds(responded.getTime() - initiated.getTime());
    }
    if (tracking.time_in_tier_resolution_seconds != null) {
      return formatDurationWithSeconds(tracking.time_in_tier_resolution_seconds * 1000);
    }
    const now = new Date();
    const started = parseDateTimeAsUTC(tracking.initiated_at);
    return formatDurationWithSeconds(now.getTime() - started.getTime());
  };

  const getTimeRemainingResponse = (): string | null => {
    if (tracking.is_responded) return null;
    if (tracking.time_remaining_response_seconds != null) {
      const str = formatDuration(Math.abs(tracking.time_remaining_response_seconds) * 1000);
      return tracking.time_remaining_response_seconds < 0 ? `${str} overdue` : `${str} left`;
    }
    const now = new Date();
    const due = parseDateTimeAsUTC(tracking.due_at);
    const diff = due.getTime() - now.getTime();
    const str = formatDuration(Math.abs(diff));
    return diff < 0 ? `${str} overdue` : `${str} left`;
  };

  const getTimeRemainingResolution = (): string | null => {
    if (tracking.is_resolved) return null;
    if (tracking.time_remaining_resolution_seconds != null) {
      const s = tracking.time_remaining_resolution_seconds;
      const str = formatDuration(Math.abs(s) * 1000);
      return s < 0 ? `${str} overdue` : `${str} left`;
    }
    if (tracking.resolution_due_at) {
      const now = new Date();
      const due = parseDateTimeAsUTC(tracking.resolution_due_at);
      const diff = due.getTime() - now.getTime();
      const str = formatDuration(Math.abs(diff));
      return diff < 0 ? `${str} overdue` : `${str} left`;
    }
    return null;
  };

  const getResponseDuration = () => {
    if (tracking.is_responded && tracking.responded_at && tracking.initiated_at) {
      const initiated = parseDateTimeAsUTC(tracking.initiated_at);
      const responded = parseDateTimeAsUTC(tracking.responded_at);
      const diff = responded.getTime() - initiated.getTime();
      return formatDuration(diff);
    }
    return null;
  };

  const getTimeToResolution = () => {
    if (tracking.is_resolved && tracking.resolved_at) {
      const initiated = parseDateTimeAsUTC(tracking.initiated_at);
      const resolved = parseDateTimeAsUTC(tracking.resolved_at);
      const diff = resolved.getTime() - initiated.getTime();
      return formatDuration(diff);
    }
    return null;
  };

  const getResolutionDuration = () => {
    if (tracking.is_resolved && tracking.resolved_at && tracking.initiated_at) {
      const initiated = parseDateTimeAsUTC(tracking.initiated_at);
      const resolved = parseDateTimeAsUTC(tracking.resolved_at);
      const diff = resolved.getTime() - initiated.getTime();
      return formatDuration(diff);
    }
    return null;
  };


  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">
              Contact: {tracking.contact_phone || tracking.contact?.phone_number || '-'}
              {tracking.contact_name || tracking.contact?.name 
                ? ` (${tracking.contact_name || tracking.contact?.name})` 
                : ''}
            </h1>
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
            Policy: {tracking.policy?.name || tracking.policy_name || tracking.policy?.code || tracking.policy_code || '-'} • Current Tier: {tracking.current_tier}
          </p>
        </div>
        <div className="flex gap-2">
          <RecordNavigation
            currentId={trackingId}
            items={navigationItems}
            basePath="/sla-management/conversation-sla-tracking"
          />
          <Button
            variant="outline"
            onClick={handleRefresh}
            disabled={isRefreshing || isLoading}
          >
            <RefreshCw className={`size-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button
            variant="destructive"
            onClick={() => setDeleteDialogOpen(true)}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="size-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation SLA Tracking</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this conversation SLA tracking record? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="event-log">Event Log</TabsTrigger>
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
                  <p className="text-sm text-muted-foreground">Time elapsed</p>
                  <p className="font-medium text-lg">
                    {getTimeElapsed() ?? '—'}
                  </p>
                </div>
                <div>
                  {tracking.is_responded ? (
                    <>
                      <p className="text-sm text-muted-foreground">Response time</p>
                      <p className={`font-medium text-lg ${(tracking.response_time ?? 0) <= (tracking.tier_response_hours ?? 0) ? 'text-green-600' : 'text-destructive'}`}>
                        {getResponseDuration() ?? (tracking.response_time != null ? formatDuration(tracking.response_time * 3600 * 1000) : '—')}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm text-muted-foreground">Time remaining (response)</p>
                      <p className={`font-medium text-lg ${getTimeRemainingResponse()?.includes('overdue') ? 'text-destructive' : ''}`}>
                        {getTimeRemainingResponse() ?? '—'}
                      </p>
                    </>
                  )}
                </div>
                <div>
                  {tracking.is_resolved ? (
                    <>
                      <p className="text-sm text-muted-foreground">Resolution time</p>
                      <p className={`font-medium text-lg ${(tracking.resolution_duration ?? 0) <= (tracking.tier_resolution_hours ?? 0) ? 'text-green-600' : 'text-destructive'}`}>
                        {getResolutionDuration() ?? (tracking.resolution_duration != null ? formatDuration(tracking.resolution_duration * 3600 * 1000) : '—')}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm text-muted-foreground">Time remaining (resolution)</p>
                      <p className={`font-medium text-lg ${getTimeRemainingResolution()?.includes('overdue') ? 'text-destructive' : ''}`}>
                        {getTimeRemainingResolution() ?? '—'}
                      </p>
                    </>
                  )}
                </div>
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
                    
                    const escalationLogs = (tracking.event_logs || []).filter((log) => log.event_type === 'escalation');

                    // Determine initial tier
                    const initialTier = escalationLogs.length > 0
                      ? escalationLogs[0].from_tier
                      : tracking.current_tier;
                    
                    // Check if current tier matches the last escalation log
                    const lastLog = escalationLogs.length > 0
                      ? escalationLogs[escalationLogs.length - 1]
                      : null;
                    const isCurrentTierInLogs = lastLog && lastLog.to_tier === tracking.current_tier;
                    
                    // Add initial tier (only if there are escalation logs, otherwise it's handled below)
                    if (escalationLogs.length > 0 && initialTier != null) {
                      timelineItems.push({
                        tier: initialTier,
                        startedAt: parseDateTimeAsUTC(tracking.initiated_at),
                        isEscalation: false,
                        isCurrent: false,
                      });
                    }
                    
                    // Add escalation logs
                    if (escalationLogs.length > 0) {
                      escalationLogs.forEach((log, index) => {
                        if (log.to_tier == null) return; // Skip if to_tier is null/undefined
                        const isLast = index === escalationLogs.length - 1;
                        timelineItems.push({
                          tier: log.to_tier,
                          startedAt: parseDateTimeAsUTC(log.event_at),
                          isEscalation: log.from_tier !== log.to_tier,
                          reason: log.reason || undefined,
                          isCurrent: isLast && log.to_tier === tracking.current_tier,
                        });
                      });
                    } else {
                      // If no escalation logs, show current tier as initial tier
                      if (tracking.current_tier != null) {
                        timelineItems.push({
                          tier: tracking.current_tier,
                          startedAt: parseDateTimeAsUTC(tracking.current_tier_started_at),
                          isEscalation: false,
                          isCurrent: true,
                        });
                      }
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
                  <p className="text-sm text-muted-foreground">Contact Phone</p>
                  <p className="font-medium">
                    {tracking.contact_phone || tracking.contact?.phone_number || '-'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Contact Name</p>
                  <p className="font-medium">
                    {tracking.contact_name || tracking.contact?.name || '-'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Policy</p>
                  <p className="font-medium">{tracking.policy?.name || tracking.policy_name || tracking.policy?.code || tracking.policy_code || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Current Tier</p>
                  <p className="font-medium">Tier {tracking.current_tier}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Assigned To</p>
                  <p className="font-medium">
                    {tracking.assigned_user_name || 
                     tracking.assigned_user?.name || 
                     tracking.assigned_user?.email || 
                     tracking.assigned_to || 
                     '-'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Initiated At</p>
                  <p className="font-medium">{formatDateTime(parseDateTimeAsUTC(tracking.initiated_at))}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Current Tier Started At</p>
                  <p className="font-medium">{formatDateTime(parseDateTimeAsUTC(tracking.current_tier_started_at))}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Due At</p>
                  <p className="font-medium">{formatDateTime(parseDateTimeAsUTC(tracking.due_at))}</p>
                </div>
                {tracking.escalated_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Escalated At</p>
                    <p className="font-medium">{formatDateTime(parseDateTimeAsUTC(tracking.escalated_at))}</p>
                  </div>
                )}
                {tracking.escalation_reason && (
                  <div className="md:col-span-2">
                    <p className="text-sm text-muted-foreground">Escalation Reason</p>
                    <p className="font-medium">{tracking.escalation_reason}</p>
                  </div>
                )}
              </div>

              {/* Response Section */}
              <div className="border-t pt-4 mt-4">
                <h3 className="text-lg font-semibold mb-4">Response</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Is Responded</p>
                    <p className="font-medium">
                      {tracking.is_responded ? (
                        <Badge variant="success" appearance="ghost">Yes</Badge>
                      ) : (
                        <Badge variant="secondary" appearance="ghost">No</Badge>
                      )}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Responded At</p>
                    <p className="font-medium">
                      {tracking.responded_at 
                        ? formatDateTime(parseDateTimeAsUTC(tracking.responded_at))
                        : '-'
                      }
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Response Duration</p>
                    <p className="font-medium">
                      {getResponseDuration() || '-'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Responded By</p>
                    <p className="font-medium">
                      {tracking.responded_by_user_name || '-'}
                    </p>
                  </div>
                  {tracking.average_response_time !== null && tracking.average_response_time !== undefined && (
                    <div>
                      <p className="text-sm text-muted-foreground">Average Response Time</p>
                      <p className="font-medium">
                        {formatDuration(tracking.average_response_time * 3600 * 1000)}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Resolution Section */}
              <div className="border-t pt-4 mt-4">
                <h3 className="text-lg font-semibold mb-4">Resolution</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Is Resolved</p>
                    <p className="font-medium">
                      {tracking.is_resolved ? (
                        <Badge variant="success" appearance="ghost">Yes</Badge>
                      ) : (
                        <Badge variant="secondary" appearance="ghost">No</Badge>
                      )}
                    </p>
                  </div>
                  {tracking.resolved_at && (
                    <div>
                      <p className="text-sm text-muted-foreground">Resolved At</p>
                      <p className="font-medium">{formatDateTime(parseDateTimeAsUTC(tracking.resolved_at))}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-sm text-muted-foreground">Resolution Duration</p>
                    <p className="font-medium">
                      {getResolutionDuration() || '-'}
                    </p>
                  </div>
                  {tracking.resolved_by_user_name || tracking.resolved_by ? (
                    <div>
                      <p className="text-sm text-muted-foreground">Resolved By</p>
                      <p className="font-medium">{tracking.resolved_by_user_name || tracking.resolved_by || '-'}</p>
                    </div>
                  ) : null}
                  {tracking.average_resolution_time !== null && tracking.average_resolution_time !== undefined && (
                    <div>
                      <p className="text-sm text-muted-foreground">Average Resolution Time</p>
                      <p className="font-medium">
                        {formatDuration(tracking.average_resolution_time * 3600 * 1000)}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Event Log */}
        <TabsContent value="event-log">
          <EventLogTable trackingId={trackingId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
