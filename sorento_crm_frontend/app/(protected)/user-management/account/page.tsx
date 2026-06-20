'use client';

import { Container } from '@/components/common/container';
import AccountProfile from './components/account-profile';
import DailySLASummaryPreference from './components/daily-sla-summary-preference';
import NotificationChannelsPreference from './components/notification-channels-preference';
import PushNotificationPreference from './components/push-notification-preference';

export default function Page() {
  return (
    <Container>
      <div className="space-y-6">
        <AccountProfile />
        <DailySLASummaryPreference />
        <NotificationChannelsPreference />
        <PushNotificationPreference />
      </div>
    </Container>
  );
}
