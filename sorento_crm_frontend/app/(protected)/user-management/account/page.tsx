'use client';

import { Container } from '@/components/common/container';
import AccountProfile from './components/account-profile';
import DailySLASummaryPreference from './components/daily-sla-summary-preference';
import NotificationChannelsPreference from './components/notification-channels-preference';
import PushNotificationPreference from './components/push-notification-preference';
import MessagePushScopePreference from './components/message-push-scope-preference';
import { CoverageSection } from '@/app/(protected)/account/notifications/components/coverage-section';

export default function Page() {
  return (
    <Container>
      <div className="space-y-6">
        <AccountProfile />
        <DailySLASummaryPreference />
        <NotificationChannelsPreference />
        <CoverageSection />
        <PushNotificationPreference />
        <MessagePushScopePreference />
      </div>
    </Container>
  );
}
