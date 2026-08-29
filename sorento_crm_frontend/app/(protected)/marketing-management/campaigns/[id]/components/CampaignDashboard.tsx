'use client';

import { useRouter } from 'next/navigation';
import { ArrowLeft, Edit } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useCampaign } from '../../hooks/useCampaigns';
import { useBackToListHref } from '@/components/common/BackToList';
import { formatDate } from '@/lib/helpers';
import BudgetTracker from './BudgetTracker';

interface CampaignDashboardProps {
  campaignId: string;
}

export default function CampaignDashboard({ campaignId }: CampaignDashboardProps) {
  const router = useRouter();
  // The list wrote its page, sort, search and status into this URL when the row
  // was clicked; Back hands the same string back rather than a fresh page 1.
  const backHref = useBackToListHref('/marketing-management/campaigns');
  const { data: campaign, isLoading } = useCampaign(campaignId);

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
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push(backHref)}>
            <ArrowLeft className="size-4" />
          </Button>
          <h1 className="text-2xl font-bold">{campaign.campaign_name}</h1>
          <Badge variant="secondary">
            {campaign.status.charAt(0).toUpperCase() + campaign.status.slice(1)}
          </Badge>
        </div>
        <Button variant="outline" onClick={() => router.push(`/marketing-management/campaigns/${campaignId}/edit`)}>
          <Edit className="size-4" />
          Edit
        </Button>
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
