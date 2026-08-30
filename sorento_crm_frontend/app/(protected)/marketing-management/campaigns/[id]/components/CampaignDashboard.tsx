'use client';

import { useRouter } from 'next/navigation';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { campaignsPagerQuery, useCampaign } from '../../hooks/useCampaigns';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import BackToList, { useBackToListHref } from '@/components/common/BackToList';
import DetailActions from '@/components/common/DetailActions';
import { formatDate } from '@/lib/helpers';
import BudgetTracker from './BudgetTracker';
import { PageHeader } from '@/components/common/PageHeader';

interface CampaignDashboardProps {
  campaignId: string;
}

export default function CampaignDashboard({ campaignId }: CampaignDashboardProps) {
  const router = useRouter();
  // The list wrote its page, sort, search and status into this URL when the row
  // was clicked; Back hands the same string back rather than a fresh page 1.
  const backHref = useBackToListHref('/marketing-management/campaigns');
  const { data: campaign, isLoading } = useCampaign(campaignId);
  // Delete asks nothing (D7): the countdown takes the primary button's place
  // and Cancel is the way back.
  const deletion = useDeferredAction({
    actionKey: 'campaign.delete',
    entityType: 'campaign',
    entityId: campaignId,
    verb: 'Deleting',
    subject: campaign ? campaign.campaign_name : '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Campaign deleted',
    invalidateKeys: [['campaigns']],
    onCommitted: () => router.push(backHref),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Campaign not found</p>
        <Button variant="outline" onClick={() => router.push(backHref)} className="mt-4">
          <ArrowLeft className="size-4" />
          Back to Campaigns
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Toolbar row: title and breadcrumb left, ONE Back right (D6, S3-01).
          The lone back-arrow button that used to sit beside the title said
          nothing about where it went and carried none of the list's state. */}
      <PageHeader
        title="Campaign"
        actions={
          <BackToList listPath="/marketing-management/campaigns" label="Back to campaigns" />
        }
      />

      {/* Record header: identity left, then pager, gear, primary. Wraps under
          the identity at 375. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h2 className="text-2xl font-bold break-words">{campaign.campaign_name}</h2>
          <Badge status={campaign.status}>
            {campaign.status.charAt(0).toUpperCase() + campaign.status.slice(1)}
          </Badge>
        </div>
        <DetailActions
          pager={{
            ...campaignsPagerQuery,
            detailPath: '/marketing-management/campaigns',
            currentId: campaignId,
            ariaLabel: 'campaign',
          }}
          actions={[
            {
              key: 'campaign.delete',
              label: 'Delete campaign',
              icon: Trash2,
              kind: 'destructive' as const,
              disabled: deletion.isPending,
              run: deletion.start,
            },
          ]}
          gearLabel="Campaign options"
          pendingAction={deletion.countdown}
          primary={
            <Button onClick={() => router.push(`/marketing-management/campaigns/${campaignId}/edit`)}>
              <Edit className="size-4" />
              Edit
            </Button>
          }
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Campaign Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Campaign Code</p>
              <p className="font-medium">{campaign.campaign_code}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Campaign Type</p>
              <p className="font-medium">{campaign.campaign_type?.type_name || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Description</p>
              <p className="font-medium">{campaign.description || '-'}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Start Date</p>
                <p className="font-medium">{formatDate(new Date(campaign.start_date))}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">End Date</p>
                <p className="font-medium">{campaign.end_date ? formatDate(new Date(campaign.end_date)) : '-'}</p>
              </div>
            </div>
            {campaign.budget && (
              <div>
                <p className="text-sm text-muted-foreground">Budget</p>
                <p className="font-medium text-lg">
                  {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(campaign.budget)}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge variant="secondary">
                {campaign.status.charAt(0).toUpperCase() + campaign.status.slice(1)}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Created</p>
              <p className="font-medium text-sm">{formatDate(new Date(campaign.created_at))}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Budget Tracker */}
      {campaign.budget && (
        <BudgetTracker campaignId={campaignId} />
      )}

      {/* TODO: Performance metrics, associated products/promotions, campaign activities, timeline, related orders */}
    </div>
  );
}
