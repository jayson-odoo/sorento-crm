/**
 * Ideas as the CRM sees them: the ss embed API's camelCase shapes relayed by the
 * CRM gateway (`/api/v1/ideation/*`, PLAN-ideation-in-crm section 10). Field names
 * follow ss `IdeaOut`, `TransitionOut`, `IdeaAttachmentOut`, `BoardColumnOut`.
 */

export type IdeaSource = 'whatsapp' | 'manual' | 'email' | 'web';

/** ss `statusColor`: a tenant-editable colour key that maps onto a CRM Badge variant. */
export type IdeaStatusColor = 'grey' | 'info' | 'primary' | 'warning' | 'success' | 'destructive';

export interface IdeaTransition {
  id: string;
  label: string;
  toStatusId: string;
  /** The tenant's display label of the target status ("Triaged"). */
  toStatusLabel: string;
}

export interface IdeaAttachment {
  id: string;
  kind: 'image' | 'audio' | 'video' | 'file';
  name: string;
  sizeBytes: number | null;
  durationSec: number | null;
}

export interface IdeaMergedInto {
  id: string;
  ideaNumber: string | null;
  title: string | null;
}

/** A Business Requirement linked to an idea, read-only here. */
export interface IdeaBusinessRequirement {
  id: string;
  title: string;
  statusLabel: string;
  statusColor: IdeaStatusColor;
}

export interface Idea {
  id: string;
  productName: string;
  /** The lifecycle key (`new`, `triaged`, ...). */
  status: string;
  statusId: string;
  statusLabel: string;
  statusColor: IdeaStatusColor;
  statusIsArchived: boolean;
  transitions: IdeaTransition[];
  advanceTransitionId: string | null;
  title: string | null;
  problem: string;
  proposedSolution: string | null;
  impact: string | null;
  department: string | null;
  rawText: string;
  source: IdeaSource;
  submitterName: string;
  upvotes: number;
  /** Upvote only: the viewer has voted or has not. */
  myVote: 'up' | null;
  priority: number;
  rank: number | null;
  attachments: IdeaAttachment[];
  createdAt: string;
  ideaNumber: string | null;
  mergedIntoId: string | null;
  mergedInto: IdeaMergedInto | null;
  mergedCount: number;
  /** CRM gateway addition: the BRs ss links to the idea (read-only BR tab). */
  businessRequirements: IdeaBusinessRequirement[];
}

export interface IdeaListParams {
  query?: string;
  /** A status key, or empty for every live idea. `archived` shows archived ones. */
  status?: string;
}

export interface IdeaStatusOption {
  value: string;
  label: string;
}

export interface IdeaBoardColumn {
  statusId: string;
  key: string;
  title: string;
  color: IdeaStatusColor;
  ideas: Idea[];
}

export interface IdeaBoard {
  columns: IdeaBoardColumn[];
}

export interface IdeaCreateInput {
  problem: string;
  proposedSolution?: string;
  impact?: string;
  department?: string;
  /** Uploaded after create through the attachments route. */
  files?: File[];
}

export interface IdeaUpdateInput {
  problem?: string;
  proposedSolution?: string | null;
  impact?: string | null;
  department?: string | null;
  rawText?: string;
}

export interface IdeaMergeInput {
  survivorId: string;
  ideaIds: string[];
}

export interface IdeaPromoteInput {
  title: string;
}

export interface IdeaComment {
  id: string;
  /** Null for a top-level comment; replies attach to the top-level one (one level). */
  parentId: string | null;
  authorName: string;
  authorIsMe: boolean;
  /** Empty when `deleted`. */
  body: string;
  createdAt: string;
  editedAt: string | null;
  /** Kept only when it still has replies; the body is then withheld. */
  deleted: boolean;
}

/** The public track page (ss `PublicIdeaStatusOut`, widened with the comments' author). */
export interface PortalIdea {
  title: string | null;
  ideaNumber: string | null;
  statusLabel: string;
  statusColor: IdeaStatusColor;
  submittedAt: string | null;
  submitterFirstName: string | null;
  upvotes: number;
}

export interface PortalIdeaComment {
  id: string;
  parentId: string | null;
  /** The idea's submitter for a public post, a staff first name for a staff one. */
  authorName: string;
  isSubmitter: boolean;
  body: string;
  createdAt: string;
  deleted: boolean;
}
