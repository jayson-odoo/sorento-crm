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
import { useConversationSLATrackingDetail, useConversationSLATracking, useDeleteConversationSLATracking, useSyncAssigneeFromRespond } from '../hooks/useConversationSLATracking';
import { formatDate, formatDateTime, formatDuration, formatDurationWithSeconds, parseDateTimeAsUTC } from '@/lib/helpers';
import EventLogTable from './EventLogTable';
import { CheckCircle, Clock, AlertCircle, RefreshCw, Trash2, ChevronDown, ChevronRight, UserRound, Info } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
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
  const [trackingOpen, setTrackingOpen] = useState(false);
  const [responseOpen, setResponseOpen] = useState(false);
  const [resolutionOpen, setResolutionOpen] = useState(false);
  const deleteMutation = useDeleteConversationSLATracking();
  const syncAssigneeMutation = useSyncAssigneeFromRespond();

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

  /** Time elapsed: stops only when resolved (resolved_at - initiated_at). Until then, keeps running (now - initiated_at). */
  const getTimeElapsed = (): string | null => {
    if (tracking.is_resolved && tracking.resolved_at && tracking.initiated_at) {
      const initiated = parseDateTimeAsUTC(tracking.initiated_at);
      const resolved = parseDateTimeAsUTC(tracking.resolved_at);
      return formatDurationWithSeconds(resolved.getTime() - initiated.getTime());
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
            variant="outline"
            onClick={() => syncAssigneeMutation.mutate(trackingId)}
            disabled={syncAssigneeMutation.isPending}
            title="Sync assignee from Respond.io"
          >
            <UserRound className={`size-4 mr-2 ${syncAssigneeMutation.isPending ? 'animate-pulse' : ''}`} />
            Sync assignee
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
          <div className="space-y-6">
          {/* Collapsible: Tracking Information */}
          <Collapsible open={trackingOpen} onOpenChange={setTrackingOpen}>
            <Card>
              <CollapsibleTrigger asChild>
                <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg flex flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-base">Tracking Information</CardTitle>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-muted-foreground">
                      Time elapsed: {getTimeElapsed() ?? '—'}
                    </span>
                    {trackingOpen ? (
                      <ChevronDown className="size-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="size-4 text-muted-foreground" />
                    )}
                  </div>
                </CardHeader>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <CardContent className="pt-0 pb-6 px-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
                    <div>
                      <div className="text-sm text-muted-foreground flex items-center gap-1.5">
                        Assigned To
                        {(tracking.assigned_user_name ?? tracking.assigned_user?.name ?? tracking.assigned_user?.email ?? tracking.assigned_to) && (
                          <Popover>
                            <PopoverTrigger asChild>
                              <button
                                type="button"
                                className="inline-flex text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                                aria-label="Show assignee email"
                              >
                                <Info className="size-4" />
                              </button>
                            </PopoverTrigger>
                            <PopoverContent className="w-auto p-3" align="start">
                              <div className="text-sm font-medium text-muted-foreground">Email</div>
                              <div className="text-sm font-medium break-all">
                                {tracking.assigned_user_email ?? tracking.assigned_user?.email ?? 'No email available'}
                              </div>
                            </PopoverContent>
                          </Popover>
                        )}
                      </div>
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
                      <p className="text-sm text-muted-foreground">Due at (response)</p>
                      <p className="font-medium">
                        {formatDateTime(parseDateTimeAsUTC(tracking.due_at))}
                        {(() => {
                          const due = parseDateTimeAsUTC(tracking.due_at).getTime();
                          const now = Date.now();
                          const overdue = tracking.is_responded && tracking.responded_at
                            ? parseDateTimeAsUTC(tracking.responded_at).getTime() > due
                            : now > due;
                          return overdue ? (
                            <span className="ml-2 text-destructive text-sm font-medium">Overdue</span>
                          ) : null;
                        })()}
                      </p>
                    </div>
                    {(tracking.due_at_resolution ?? tracking.resolution_due_at) && (
                      <div>
                        <p className="text-sm text-muted-foreground">Due at (resolution)</p>
                        <p className="font-medium">
                          {formatDateTime(parseDateTimeAsUTC(tracking.due_at_resolution ?? tracking.resolution_due_at!))}
                          {(() => {
                            const dueRes = tracking.due_at_resolution ?? tracking.resolution_due_at;
                            if (!dueRes) return null;
                            const due = parseDateTimeAsUTC(dueRes).getTime();
                            const now = Date.now();
                            const overdue = tracking.is_resolved && tracking.resolved_at
                              ? parseDateTimeAsUTC(tracking.resolved_at).getTime() > due
                              : now > due;
                            return overdue ? (
                              <span className="ml-2 text-destructive text-sm font-medium">Overdue</span>
                            ) : null;
                          })()}
                        </p>
                      </div>
                    )}
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
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>

          {/* Collapsible: Response time */}
          <Collapsible open={responseOpen} onOpenChange={setResponseOpen}>
            <Card>
              <CollapsibleTrigger asChild>
                <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg flex flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-base">Response time</CardTitle>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${getTimeRemainingResponse()?.includes('overdue') ? 'text-destructive' : ''}`}>
                      {tracking.is_responded
                        ? (getResponseDuration() ?? (tracking.response_time != null ? formatDuration(tracking.response_time * 3600 * 1000) : '—'))
                        : (getTimeRemainingResponse() ?? '—')}
                    </span>
                    {responseOpen ? (
                      <ChevronDown className="size-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="size-4 text-muted-foreground" />
                    )}
                  </div>
                </CardHeader>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <CardContent className="pt-0 pb-6 px-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
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
                          : '-'}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Response Duration</p>
                      <p className="font-medium">{getResponseDuration() || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Responded By</p>
                      <p className="font-medium">{tracking.responded_by_user_name || '-'}</p>
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
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>

          {/* Collapsible: Resolution time */}
          <Collapsible open={resolutionOpen} onOpenChange={setResolutionOpen}>
            <Card>
              <CollapsibleTrigger asChild>
                <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg flex flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-base">Resolution time</CardTitle>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${getTimeRemainingResolution()?.includes('overdue') ? 'text-destructive' : ''}`}>
                      {tracking.is_resolved
                        ? (getResolutionDuration() ?? (tracking.resolution_duration != null ? formatDuration(tracking.resolution_duration * 3600 * 1000) : '—'))
                        : (getTimeRemainingResolution() ?? '—')}
                    </span>
                    {resolutionOpen ? (
                      <ChevronDown className="size-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="size-4 text-muted-foreground" />
                    )}
                  </div>
                </CardHeader>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <CardContent className="pt-0 pb-6 px-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
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
                    <div>
                      <p className="text-sm text-muted-foreground">Resolved At</p>
                      <p className="font-medium">
                        {tracking.resolved_at
                          ? formatDateTime(parseDateTimeAsUTC(tracking.resolved_at))
                          : '-'}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Resolution Duration</p>
                      <p className="font-medium">{getResolutionDuration() || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Resolved By</p>
                      <p className="font-medium">{tracking.resolved_by_user_name || tracking.resolved_by || '-'}</p>
                    </div>
                    {tracking.average_resolution_time !== null && tracking.average_resolution_time !== undefined && (
                      <div>
                        <p className="text-sm text-muted-foreground">Average Resolution Time</p>
                        <p className="font-medium">
                          {formatDuration(tracking.average_resolution_time * 3600 * 1000)}
                        </p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>
          </div>
        </TabsContent>

        {/* Tab 2: Event Log */}
        <TabsContent value="event-log">
          <EventLogTable trackingId={trackingId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
