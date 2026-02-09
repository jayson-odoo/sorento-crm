'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useCampaign } from '../../hooks/useCampaigns';

interface BudgetTrackerProps {
  campaignId: string;
}

export default function BudgetTracker({ campaignId }: BudgetTrackerProps) {
  const { data: campaign } = useCampaign(campaignId);

  if (!campaign?.budget_tracker) {
    return null;
  }

  const { total_budget, spent_to_date, remaining_budget, progress_percent, burn_rate } = campaign.budget_tracker;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Budget Tracking</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-muted-foreground">Total Budget</p>
            <p className="font-medium text-lg">
              {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(total_budget)}
            </p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Spent to Date</p>
            <p className="font-medium text-lg">
              {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(spent_to_date)}
            </p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Remaining</p>
            <p className="font-medium text-lg">
              {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(remaining_budget)}
            </p>
          </div>
        </div>
        <div>
          <div className="flex justify-between text-sm mb-2">
            <span>Progress</span>
            <span>{progress_percent.toFixed(1)}%</span>
          </div>
          <Progress value={progress_percent} />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Burn Rate</p>
          <p className="font-medium">
            {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(burn_rate)} / day
          </p>
        </div>
        {progress_percent > 90 && (
          <div className="text-sm text-warning">
            Warning: Budget is {progress_percent.toFixed(1)}% spent
          </div>
        )}
      </CardContent>
    </Card>
  );
}
