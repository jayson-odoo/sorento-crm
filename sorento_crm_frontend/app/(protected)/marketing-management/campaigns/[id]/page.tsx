import { use } from 'react';
import CampaignDashboard from './components/CampaignDashboard';

export default function CampaignDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <CampaignDashboard campaignId={id} />;
}
