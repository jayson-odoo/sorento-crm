'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { ContentLoader } from '@/components/common/content-loader';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { SystemSetting } from '@/app/models/system';
import { SettingsProvider } from './components/settings-context';

type NavRoutes = Record<
  string,
  {
    title: string;
    path: string;
  }
>;

/** Map API snake_case settings to frontend camelCase SystemSetting */
function mapSettingsFromApi(raw: Record<string, unknown> | null): SystemSetting | null {
  if (!raw || typeof raw !== 'object') return null;
  return {
    ...raw,
    id: raw.id as string,
    name: (raw.name as string) ?? '',
    logo: (raw.logo as string | null) ?? null,
    active: Boolean(raw.active),
    address: (raw.address as string | null) ?? null,
    websiteURL: (raw.website_url as string | null) ?? null,
    supportEmail: (raw.support_email as string | null) ?? null,
    supportPhone: (raw.support_phone as string | null) ?? null,
    language: (raw.language as string) ?? 'en',
    timezone: (raw.timezone as string) ?? 'Europe/London',
    currency: (raw.currency as string) ?? 'MYR',
    currencyFormat: (raw.currency_format as string) ?? 'RM {value}',
    defaultProductSupplierId: (raw.default_product_supplier_id as string | null) ?? null,
    defaultProductStandardLeadTimeDays:
      typeof raw.default_product_standard_lead_time_days === 'number'
        ? raw.default_product_standard_lead_time_days
        : 90,
    // A new settings column reaches the FE only if it is in this manual mapper too.
    defaultUomId: (raw.default_uom_id as string | null) ?? null,
    defaultUomCode: (raw.default_uom_code as string | null) ?? null,
    takeoverCooldownSeconds:
      typeof raw.takeover_cooldown_seconds === 'number'
        ? raw.takeover_cooldown_seconds
        : 60,
    formSlaGraceSeconds:
      typeof raw.form_sla_grace_seconds === 'number' ? raw.form_sla_grace_seconds : 0,
    // A new settings column reaches the FE only if it is in this manual mapper too.
    planGrain: raw.plan_grain === 'location' ? 'location' : 'product',
    purchaseRequestDefaultApproverUserId:
      (raw.purchase_request_default_approver_user_id as string | null) ?? null,
    purchaseRequestDefaultApproverName:
      (raw.purchase_request_default_approver_name as string | null) ?? null,
    purchaseRequestDefaultApproverEmail:
      (raw.purchase_request_default_approver_email as string | null) ?? null,
    sponsorshipFormDefaultApproverUserId:
      (raw.sponsorship_form_default_approver_user_id as string | null) ?? null,
    sponsorshipFormDefaultApproverName:
      (raw.sponsorship_form_default_approver_name as string | null) ?? null,
    sponsorshipFormDefaultApproverEmail:
      (raw.sponsorship_form_default_approver_email as string | null) ?? null,
    n8nAttachmentWebhookUrl: (raw.n8n_attachment_webhook_url as string | null) ?? null,
    n8nCrmChatOutboundWebhookUrl: (raw.n8n_crm_chat_outbound_webhook_url as string | null) ?? null,
    n8nStockInquiryReviseWebhookUrl:
      (raw.n8n_stock_inquiry_revise_webhook_url as string | null) ?? null,
    complaintDoDeliveredNotifyTiers:
      (raw.complaint_do_delivered_notify_tiers as string) ?? '1,2',
    handlingLockEnabledTypes: Array.isArray(raw.handling_lock_enabled_types)
      ? (raw.handling_lock_enabled_types as string[])
      : [],
    // Portal submission revisions. Both columns are on the GET dict AND on
    // SystemSettingUpdate server-side; they must appear in this manual mapper too
    // or the UI would always render the default rather than the saved value.
    portalRevisionsEnabled:
      typeof raw.portal_revisions_enabled === 'boolean'
        ? raw.portal_revisions_enabled
        : true,
    portalMaxRevisions:
      typeof raw.portal_max_revisions === 'number' ? raw.portal_max_revisions : 2,
    healthDigestEnabled: Boolean(raw.health_digest_enabled),
    healthAlertsEnabled: Boolean(raw.health_alerts_enabled),
    healthNotifyRoleIds: Array.isArray(raw.health_notify_role_ids)
      ? (raw.health_notify_role_ids as string[])
      : [],
    healthNotifyUserIds: Array.isArray(raw.health_notify_user_ids)
      ? (raw.health_notify_user_ids as string[])
      : [],
    healthIntegrationFailThreshold:
      typeof raw.health_integration_fail_threshold === 'number'
        ? raw.health_integration_fail_threshold
        : 10,
    healthAuditVolumeFloor:
      typeof raw.health_audit_volume_floor === 'number'
        ? raw.health_audit_volume_floor
        : 0,
    chatLatencyTargetSeconds:
      typeof raw.chat_latency_p99_target_seconds === 'number'
        ? raw.chat_latency_p99_target_seconds
        : 10,
    chatLatencyPercentile:
      typeof raw.chat_latency_percentile === 'number' ? raw.chat_latency_percentile : 99,
    chatLatencyCeilingMultiplier:
      typeof raw.chat_latency_ceiling_multiplier === 'number'
        ? raw.chat_latency_ceiling_multiplier
        : 3,
    chatLatencyNoReplyMinutes:
      typeof raw.chat_latency_no_reply_minutes === 'number'
        ? raw.chat_latency_no_reply_minutes
        : 5,
    chatLatencyMinSample:
      typeof raw.chat_latency_min_sample === 'number' ? raw.chat_latency_min_sample : 30,
    smtp: raw.smtp as SystemSetting['smtp'] ?? null,
  } as SystemSetting;
}

const fetchSettings = async () => {
  const response = await apiFetch('/api/user-management/settings');
  if (!response.ok) {
    throw new Error('Failed to fetch settings');
  }
  const data = await response.json();
  return {
    settings: mapSettingsFromApi(data.settings ?? null),
    roles: data.roles ?? [],
  };
};

function createDefaultSettings(): SystemSetting {
  return {
    id: '',
    name: '',
    logo: null,
    active: true,
    address: null,
    websiteURL: null,
    supportEmail: null,
    supportPhone: null,
    language: 'en',
    timezone: 'Europe/London',
    currency: 'MYR',
    currencyFormat: 'RM {value}',
    defaultProductSupplierId: null,
    defaultProductStandardLeadTimeDays: 90,
    defaultUomId: null,
    defaultUomCode: null,
    takeoverCooldownSeconds: 60,
    formSlaGraceSeconds: 0,
    planGrain: 'product',
    purchaseRequestDefaultApproverUserId: null,
    purchaseRequestDefaultApproverName: null,
    purchaseRequestDefaultApproverEmail: null,
    sponsorshipFormDefaultApproverUserId: null,
    sponsorshipFormDefaultApproverName: null,
    sponsorshipFormDefaultApproverEmail: null,
    n8nAttachmentWebhookUrl: null,
    n8nCrmChatOutboundWebhookUrl: null,
    n8nStockInquiryReviseWebhookUrl: null,
    notifyStockEmail: false,
    notifyStockWeb: false,
    notifyStockThreshold: 0,
    notifyStockRoleIds: [],
    notifyNewOrderEmail: false,
    notifyNewOrderWeb: false,
    notifyNewOrderRoleIds: [],
    notifyOrderStatusUpdateEmail: false,
    notifyOrderStatusUpdateWeb: false,
    notifyOrderStatusUpdateRoleIds: [],
    notifyPaymentFailureEmail: false,
    notifyPaymentFailureWeb: false,
    notifyPaymentFailureRoleIds: [],
    notifySystemErrorFailureEmail: false,
    notifySystemErrorWeb: false,
    notifySystemErrorRoleIds: [],
    complaintDoDeliveredNotifyTiers: '1,2',
    handlingLockEnabledTypes: [],
    portalRevisionsEnabled: true,
    portalMaxRevisions: 2,
    healthDigestEnabled: false,
    healthAlertsEnabled: false,
    healthNotifyRoleIds: [],
    healthNotifyUserIds: [],
    healthIntegrationFailThreshold: 10,
    healthAuditVolumeFloor: 0,
    chatLatencyTargetSeconds: 10,
    chatLatencyPercentile: 99,
    chatLatencyCeilingMultiplier: 3,
    chatLatencyNoReplyMinutes: 5,
    chatLatencyMinSample: 30,
    smtp: null,
  };
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const { data = { settings: null, roles: [] }, isLoading } = useQuery({
    queryKey: ['system-settings'],
    queryFn: fetchSettings,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });

  const roles = data.roles ?? [];
  const settings = data.settings ?? createDefaultSettings();

  const navRoutes = useMemo<NavRoutes>(
    () => ({
      general: {
        title: 'General',
        path: '/user-management/settings',
      },
      notifications: {
        title: 'Notifications',
        path: '/user-management/settings/notifications',
      },
      complaints: {
        title: 'Complaints',
        path: '/user-management/settings/complaints',
      },
      'portal-revisions': {
        title: 'Portal Revisions',
        path: '/user-management/settings/portal-revisions',
      },
      'chatbot-media': {
        title: 'Chatbot Media',
        path: '/user-management/settings/chatbot-media',
      },
      'system-health': {
        title: 'System Health',
        path: '/user-management/settings/system-health',
      },
      smtp: {
        title: 'SMTP',
        path: '/user-management/settings/smtp',
      },
      social: {
        title: 'Social',
        path: '/user-management/settings/social',
      },
      integrations: {
        title: 'Integrations',
        path: '/user-management/settings/integrations',
      },
    }),
    [],
  );

  // Local state to instantly update the active tab on click
  const [activeTab, setActiveTab] = useState<string>('');

  // Keep the local state in sync with the current pathname, in case navigation happens externally
  useEffect(() => {
    const found = Object.keys(navRoutes).find(
      (key) => pathname === navRoutes[key].path,
    );
    if (found) {
      setActiveTab(found);
    } else {
      setActiveTab('general');
    }
  }, [navRoutes, pathname]);

  // Handle tab click: update local state immediately and trigger navigation
  const handleTabClick = (key: string, path: string) => {
    setActiveTab(key);
    // Navigate after a short delay (or immediately) so that the UI updates first
    router.push(path);
  };

  if (isLoading) {
    return <ContentLoader className="mt-[30%]" />;
  }

  return (
    <SettingsProvider settings={settings} roles={roles}>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Settings</ToolbarTitle>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
      </Container>
      <Container>
        <Tabs defaultValue={activeTab} value={activeTab} className="space-y-5">
          <TabsList variant="line">
            {Object.entries(navRoutes).map(([key, { title, path }]) => (
              <TabsTrigger
                key={key}
                value={key}
                disabled={isLoading}
                onClick={() => handleTabClick(key, path)}
                className="justify-start"
              >
                {title}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="grow mt-5">{children}</div>
      </Container>
    </SettingsProvider>
  );
}
