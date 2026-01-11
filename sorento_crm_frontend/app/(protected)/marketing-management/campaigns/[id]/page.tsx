import CampaignDashboard from './components/CampaignDashboard';

export default function CampaignDetailPage({ params }: { params: { id: string } }) {
  return <CampaignDashboard campaignId={params.id} />;
}
