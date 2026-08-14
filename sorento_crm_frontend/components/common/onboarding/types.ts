/**
 * The onboarding intake/review vocabulary, shared by the public intake page
 * (`app/(auth)/onboarding`) and the captain's review screens
 * (`app/(protected)/user-management/onboarding-requests`).
 *
 * It lives in `components/common` rather than beside either screen because the
 * SAME grid renders on both, and a type that only one side owned is how the two
 * views start drifting - the failure the shared `RespondChatList` exists to
 * prevent.
 *
 * Contract: `documentation/plans/UAC-onboarding-intake.md`.
 */

/** Where a provisioning lane has got to. See UAC AC-1.2. */
export type OnboardingLaneStep =
  | 'pending'
  | 'done'
  | 'failed'
  | 'skipped'
  /** Contact lane, Slice 2. */
  | 'created_local'
  | 'pushed'
  /** Agent-seat lane, Slice 3. */
  | 'awaiting_invite'
  | 'linked';

/** The captain's verdict on one person. */
export type OnboardingReviewStatus = 'proposed' | 'approved' | 'rejected' | 'on_hold';

/** The seeded `onboarding_request` status graph (UAC AC-2.2). */
export type OnboardingRequestStatus =
  | 'draft'
  | 'sent'
  | 'submitted'
  | 'in_review'
  | 'processing'
  | 'completed'
  | 'partially_completed'
  | 'rejected'
  | 'cancelled';

export const ONBOARDING_STATUS_LABELS: Record<OnboardingRequestStatus, string> = {
  draft: 'Draft',
  sent: 'Link sent',
  submitted: 'Submitted',
  in_review: 'In review',
  processing: 'Provisioning',
  completed: 'Completed',
  partially_completed: 'Completed with failures',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
};

/**
 * A collision against a live unique key, computed at read time and never stored
 * (UAC AC-6.4). An existing artifact is NOT an error - it pre-decides that lane
 * as `skipped`, so onboarding someone who half-exists fills in the rest.
 */
export interface OnboardingCollision {
  kind: 'user_email' | 'user_phone' | 'contact_phone';
  /** Human-readable, already resolved server-side. Never an id (cursor rule). */
  label: string;
}

/** What the requester may see of a template: a label. Never roles (UAC AC-5.4). */
export interface OnboardingTemplateOption {
  id: string;
  name: string;
  description: string | null;
  default_needs_system_account: boolean;
  default_needs_respond_contact: boolean;
  default_needs_agent_seat: boolean;
}

export interface OnboardingPerson {
  id: string;
  row_number: number;
  full_name: string;
  nick_name: string | null;
  /** What was typed or read off the sheet. The normalised form stays server-side. */
  phone_raw: string | null;
  email_raw: string | null;
  /** The sheet's section header, e.g. "SALES PERSON". The only access signal it carries. */
  section_label: string | null;
  template_id: string | null;
  requester_note: string | null;
  reviewer_note: string | null;
  needs_system_account: boolean;
  needs_respond_contact: boolean;
  needs_agent_seat: boolean;
  review_status: OnboardingReviewStatus;
  rejection_reason: string | null;
  /** Non-fatal parse complaints for this row, e.g. "phone not recognised". */
  problems: string[];
  /** Review-time only; empty on the intake page. */
  collisions: OnboardingCollision[];
  user_step: OnboardingLaneStep;
  user_error: string | null;
  /** Resolved display name of the user this row produced or matched. Never an id. */
  user_label: string | null;
  contact_step: OnboardingLaneStep;
  contact_error: string | null;
  agent_step: OnboardingLaneStep;
  agent_error: string | null;
}

/** Row shape returned by the parse endpoint, before it becomes a person row. */
export interface OnboardingParsedRow {
  row_number: number;
  full_name: string;
  nick_name: string | null;
  phone_raw: string | null;
  email_raw: string | null;
  section_label: string | null;
  problems: string[];
}

export interface OnboardingParseResult {
  rows: OnboardingParsedRow[];
  /** Rows the reader could not turn into a person at all. */
  problems: Array<{ row: number; reason: string }>;
  unmapped_headers: string[];
  missing_columns: string[];
  total_rows: number;
  sections: string[];
}

/** What the public intake page is handed for its whole session. */
export interface OnboardingIntakeContext {
  title: string;
  company_name: string;
  requester_name: string;
  requester_email: string;
  status: OnboardingRequestStatus;
  expires_at: string;
  /** False once submitted, revoked or expired: the page becomes a status view. */
  editable: boolean;
  requester_note: string | null;
  templates: OnboardingTemplateOption[];
  people: OnboardingPerson[];
}

export interface OnboardingRequestSummary {
  id: string;
  title: string;
  company_name: string;
  requester_name: string;
  requester_email: string;
  status: OnboardingRequestStatus;
  people_count: number;
  approved_count: number;
  rejected_count: number;
  submitted_at: string | null;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
}

export interface OnboardingRequestDetail extends OnboardingRequestSummary {
  reviewer_note: string | null;
  requester_note: string | null;
  reviewed_by_name: string | null;
  provisioned_at: string | null;
  source_file_name: string | null;
  templates: OnboardingTemplateOption[];
  people: OnboardingPerson[];
}

/** The subset of a person row either screen may edit. */
export type OnboardingPersonPatch = Partial<
  Pick<
    OnboardingPerson,
    | 'full_name'
    | 'nick_name'
    | 'phone_raw'
    | 'email_raw'
    | 'template_id'
    | 'needs_system_account'
    | 'needs_respond_contact'
    | 'needs_agent_seat'
    | 'requester_note'
    | 'reviewer_note'
  >
>;
