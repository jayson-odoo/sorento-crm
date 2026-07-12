import { SystemSetting } from './system';

// Enums
export enum UserStatus {
  INACTIVE = 'INACTIVE',
  ACTIVE = 'ACTIVE',
  BLOCKED = 'BLOCKED',
}

// Models
export interface UserRoleSimple {
  id: string;
  name: string;
}

export interface User {
  id: string;
  email: string;
  password?: string | null;
  country?: string | null;
  timezone?: string | null;
  name?: string | null;
  /** Optional contact phone number for the user. */
  contactNumber?: string | null;
  roleId?: string | null;
  status: UserStatus;
  createdAt: Date;
  updatedAt: Date;
  lastSignInAt?: Date | null;
  emailVerifiedAt?: Date | null;
  isTrashed: boolean;
  avatar?: string | null;
  invitedByUserId?: string | null;
  isProtected: boolean;
  respondUserId?: string | null;
  respondSynced?: string | null;
  superiorId?: string | null;
  superiorName?: string | null;
  /** Conversation SLA policy tier (1, 2, ...) */
  tier?: number | null;
  dailySlaSummarySubscribed?: boolean | null;
  daily_sla_summary_subscribed?: boolean | null;
  /** Linked WhatsApp contact (resolves respond_io_id for outbound WhatsApp). */
  respondContactId?: string | null;
  respond_contact_id?: string | null;
  /** Escalation + assignment WhatsApp pings. */
  notifyWhatsapp?: boolean | null;
  notify_whatsapp?: boolean | null;
  /** Daily SLA summary WhatsApp template. */
  notifyWhatsappSummary?: boolean | null;
  notify_whatsapp_summary?: boolean | null;
  /** Per-event SLA notify toggles. */
  notifyEmailOnAssignment?: boolean | null;
  notify_email_on_assignment?: boolean | null;
  notifyEmailOnEscalation?: boolean | null;
  notify_email_on_escalation?: boolean | null;
  notifyWhatsappOnAssignment?: boolean | null;
  notify_whatsapp_on_assignment?: boolean | null;
  notifyWhatsappOnEscalation?: boolean | null;
  notify_whatsapp_on_escalation?: boolean | null;
  notifyEmailOnDeadlineExtended?: boolean | null;
  notify_email_on_deadline_extended?: boolean | null;
  notifyWhatsappOnDeadlineExtended?: boolean | null;
  notify_whatsapp_on_deadline_extended?: boolean | null;
  notifyEmailOnHandling?: boolean | null;
  notify_email_on_handling?: boolean | null;
  notifyWhatsappOnHandling?: boolean | null;
  notify_whatsapp_on_handling?: boolean | null;
  /** Product-discontinued batch notification opt-in (admin-configured). */
  notifyEmailOnProductDiscontinued?: boolean | null;
  notify_email_on_product_discontinued?: boolean | null;
  notifyWhatsappOnProductDiscontinued?: boolean | null;
  notify_whatsapp_on_product_discontinued?: boolean | null;
  roles?: UserRoleSimple[];
  role?: UserRole;
  sessions?: Session[];
  accounts?: Account[];
}

export interface UserRole {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  isTrashed: boolean;
  createdByUserId?: string | null;
  createdAt: Date;
  isProtected: boolean;
  isDefault: boolean;
  createdByUser?: User | null;
  users?: User[];
  permissions?: UserRolePermission[];
  settings?: SystemSetting[];
}

export interface UserPermission {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  createdByUserId?: string | null;
  createdAt: Date;
  createdByUser?: User | null;
  roles?: UserRolePermission[];
}

export interface UserRolePermission {
  id: string;
  roleId: string;
  permissionId: string;
  assignedAt: Date;
  role?: UserRole;
  permission?: UserPermission;
}

export interface UserAddress {
  id: string;
  userId: string;
  addressLine: string;
  addressLine2?: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
  isDefault: boolean;
  user?: User;
}
export interface Account {
  id: string;
  userId: string;
  type: string;
  provider: string;
  providerAccountId: string;
  refresh_token?: string | null;
  access_token?: string | null;
  expires_at?: number | null;
  token_type?: string | null;
  scope?: string | null;
  id_token?: string | null;
  session_state?: string | null;
  user?: User;
}

export interface Session {
  id: string;
  sessionToken: string;
  userId: string;
  expires: Date;
  user?: User;
}

export interface VerificationToken {
  identifier: string;
  token: string;
  expires: Date;
}
