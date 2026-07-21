import { User } from './user';

// Models
export interface SystemLog {
  id: string;
  event: string;
  userId: string;
  createdAt: Date;
  entityId?: string | null;
  entityType?: string | null;
  description?: string | null;
  ipAddress?: string | null;
  user?: User;
  meta?: JSON;
}

export interface SystemSetting {
  id: string;
  name: string;
  logo?: string | null;
  active: boolean;
  address?: string | null;
  websiteURL?: string | null;
  supportEmail?: string | null;
  supportPhone?: string | null;
  language: string;
  timezone: string;
  currency: string;
  currencyFormat: string;

  defaultProductSupplierId?: string | null;
  defaultProductStandardLeadTimeDays?: number;

  /** Takeover cooldown window in seconds (0 = instant takeover). */
  takeoverCooldownSeconds?: number;

  /** System default approver for procurement "Send for approval" (skips chooser when set). */
  purchaseRequestDefaultApproverUserId?: string | null;
  purchaseRequestDefaultApproverName?: string | null;
  purchaseRequestDefaultApproverEmail?: string | null;
  sponsorshipFormDefaultApproverUserId?: string | null;
  sponsorshipFormDefaultApproverName?: string | null;
  sponsorshipFormDefaultApproverEmail?: string | null;

  /** When set, used for attachment upload webhooks; otherwise backend may use N8N_WEBHOOK_URL env. */
  n8nAttachmentWebhookUrl?: string | null;
  /** Webhook for CRM Chat Records replies (Respond.io-shaped payload for n8n). */
  n8nCrmChatOutboundWebhookUrl?: string | null;
  /** Webhook for public rejected stock inquiry revise requests. */
  n8nStockInquiryReviseWebhookUrl?: string | null;

  socialFacebook?: string | null;
  socialTwitter?: string | null;
  socialInstagram?: string | null;
  socialLinkedIn?: string | null;
  socialPinterest?: string | null;
  socialYoutube?: string | null;

  notifyStockEmail: boolean;
  notifyStockWeb: boolean;
  notifyStockThreshold: number;
  notifyStockRoleIds: string[];

  notifyNewOrderEmail: boolean;
  notifyNewOrderWeb: boolean;
  notifyNewOrderRoleIds: string[];

  notifyOrderStatusUpdateEmail: boolean;
  notifyOrderStatusUpdateWeb: boolean;
  notifyOrderStatusUpdateRoleIds: string[];

  notifyPaymentFailureEmail: boolean;
  notifyPaymentFailureWeb: boolean;
  notifyPaymentFailureRoleIds: string[];

  notifySystemErrorFailureEmail: boolean;
  notifySystemErrorWeb: boolean;
  notifySystemErrorRoleIds: string[];

  // Complaint <-> DO auto-fulfilment: comma list of Complaint-team tiers (e.g. "1,2")
  // that receive the replacement-DO-delivered notification.
  complaintDoDeliveredNotifyTiers: string;

  // Form handling-lock ("I'm handling this"): the source_entity_types the per-form lock
  // is enabled for (e.g. ["complaint", "stock_inquiry"]). Empty = lock off everywhere.
  handlingLockEnabledTypes: string[];
  // System Health observability (daily digest + immediate anomaly alerts).
  /** Send the daily system-health digest (in-app + email) to the notify roles. */
  healthDigestEnabled: boolean;
  /** Send off-cycle anomaly alerts (n8n down, task failed/overdue, integration spike). */
  healthAlertsEnabled: boolean;
  /** Roles that receive the digest + alerts. */
  healthNotifyRoleIds: string[];
  /** Individual users that receive the digest + alerts (unioned with role members). */
  healthNotifyUserIds: string[];
  /** Failed-integration count within the window that trips an immediate alert. */
  healthIntegrationFailThreshold: number;
  /** Expected minimum daily audit-event volume; 0 disables the low-volume warning. */
  healthAuditVolumeFloor: number;

  /** WhatsApp round-trip SLA: the latency target the chosen percentile is held to. */
  chatLatencyTargetSeconds: number;
  /** Which computed percentile alerts (50 / 95 / 99). p50 and p95 are always shown. */
  chatLatencyPercentile: number;
  /** Per-turn hard ceiling = target x this. Fires on ONE bad turn, no minimum sample. */
  chatLatencyCeilingMultiplier: number;
  /** Minutes an incoming message may sit unanswered before alerting. */
  chatLatencyNoReplyMinutes: number;
  /** Below this many turns no percentile is claimed, so the window stays quiet. */
  chatLatencyMinSample: number;

  smtp?: {
    smtp_host?: string | null;
    smtp_port?: string | null;
    smtp_secure?: boolean;
    smtp_username?: string | null;
    smtp_from?: string | null;
    smtp_password?: null; // never returned
  } | null;
}
