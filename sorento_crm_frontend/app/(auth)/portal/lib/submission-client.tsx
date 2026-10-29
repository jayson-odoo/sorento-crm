'use client';

/**
 * The API a portal form talks to (PORTAL-P4-REQUESTS R1, form parity).
 *
 * SubmissionForm and its children (AttachmentDropzone, LookupSelect, DOFilterMultiSelect,
 * PortalSubmissionComments, RevisionHistory, `useRevisions`, AIExtractDialog) read every call
 * through `useSubmissionClient()`. With no provider that is portal-client itself, so the portal is
 * unchanged. A CRM page wraps the same form in `SubmissionClientProvider` with the My Requests
 * client (`services/myRequestsSubmissionClient.ts`), so a salesperson's form is the portal's own.
 *
 * Members are read where they are called, never destructured up front: a test that mocks
 * portal-client with only the functions it needs must keep working.
 *
 * The kinds with pages of their own (Sample Request, New Product Application, Sales Opportunity,
 * Price Tag Request; R3) read their own service the same way, through `clientService`: absent, the
 * portal's module.
 */
import { createContext, useContext, type ComponentType, type ReactNode } from 'react';
import type { AttachmentPreviewItem } from '@/components/common/AttachmentPreviewModal';
import * as portalClient from './portal-client';
import type { PortalAttachment, PortalLandingKind } from './portal-client';
import { portalFetchBytes } from './portal-preview';
import type { NewProductApplicationService } from './new-product-application-service';
import type { PriceTagRequestService } from './price-tag-request-service';
import type { SalesOpportunityService } from './sales-opportunity-service';
import type { SampleRequestService } from './sample-request-service';

/** The portal-client functions a portal form and its children call. */
export type SubmissionApi = Pick<
  typeof portalClient,
  | 'fetchMe'
  | 'fetchSubmission'
  | 'fetchSubmissionNeighbours'
  | 'fetchRequestorOptions'
  | 'lookupProducts'
  | 'lookupDebtors'
  | 'lookupProjects'
  | 'lookupDeliveryOrders'
  | 'lookupSet'
  | 'saveDraft'
  | 'submitDraft'
  | 'deleteDraftSubmission'
  | 'saveRevisionDraft'
  | 'discardRevisionDraft'
  | 'fetchRevisions'
  | 'reviseSubmission'
  | 'uploadAttachment'
  | 'deleteAttachment'
  | 'fetchSubmissionComments'
  | 'postSubmissionComment'
  | 'editSubmissionComment'
  | 'deleteSubmissionComment'
  | 'aiExtractFromFiles'
  | 'portalAttachmentDownloadUrl'
  | 'fetchPortalAttachmentBytes'
  | 'getPriceTagDesign'
>;

/** Where the form's own links and redirects go. Absent: the portal's paths. */
export interface SubmissionPaths {
  /** The list of this kind: Back, Cancel, and after a save, submit or delete. */
  home: (kind: PortalLandingKind) => string;
  detail: (kind: PortalLandingKind, id: string) => string;
  duplicate: (kind: PortalLandingKind, id: string) => string;
}

/** A draft's delete, rendered in place of the portal's confirm-and-delete button. */
export interface DraftDeleteProps {
  kind: PortalLandingKind;
  submissionId: string;
  disabled: boolean;
  /** The delete has committed: leave the record. */
  onDeleted: () => void;
}

/** An own upload's remove, rendered in place of the portal's confirm-and-remove button. */
export interface AttachmentRemoveProps {
  kind: PortalLandingKind;
  attachment: PortalAttachment;
  disabled?: boolean;
  /** The removal has committed: drop the row. */
  onRemoved: () => void;
}

export interface SubmissionClient extends SubmissionApi {
  paths?: SubmissionPaths;
  /**
   * How deletes behave. Absent: the portal's (a confirm, then the DELETE). The CRM parks them
   * on the server instead (D7): the button becomes a countdown with a Cancel.
   */
  deletes?: {
    DraftDelete: ComponentType<DraftDeleteProps>;
    AttachmentRemove: ComponentType<AttachmentRemoveProps>;
  };
  /** Inside a CRM page: its header carries Back, so the form shows no Back of its own, and the
   *  prev / next chevrons sit inline instead of on the window's edges. */
  embedded?: boolean;
  /** The services of the kinds with pages of their own. Absent: the portal's own modules. */
  sampleRequest?: SampleRequestService;
  newProductApplication?: NewProductApplicationService;
  salesOpportunity?: SalesOpportunityService;
  priceTagRequest?: PriceTagRequestService;
}

type KindServiceKey =
  | 'sampleRequest'
  | 'newProductApplication'
  | 'salesOpportunity'
  | 'priceTagRequest';

const SubmissionClientContext = createContext<SubmissionClient | null>(null);

export function SubmissionClientProvider({
  client,
  children,
}: {
  client: SubmissionClient;
  children: ReactNode;
}) {
  return (
    <SubmissionClientContext.Provider value={client}>{children}</SubmissionClientContext.Provider>
  );
}

/** The provided client, or portal-client itself. */
export function useSubmissionClient(): SubmissionClient {
  return useContext(SubmissionClientContext) ?? (portalClient as SubmissionClient);
}

/** An optional member, read with `in`: a mocked portal-client throws on a missing key. */
function extra<K extends 'paths' | 'deletes' | 'embedded' | KindServiceKey>(
  client: SubmissionClient,
  key: K,
): SubmissionClient[K] | undefined {
  return key in client ? client[key] : undefined;
}

export function clientPaths(client: SubmissionClient): SubmissionPaths | undefined {
  return extra(client, 'paths');
}

export function clientDeletes(client: SubmissionClient): SubmissionClient['deletes'] {
  return extra(client, 'deletes');
}

export function clientEmbedded(client: SubmissionClient): boolean {
  return extra(client, 'embedded') === true;
}

/** A kind's service: the client's, or `portal` (that kind's own module). Call it where the call is
 *  made, never up front, so a test mocking the module with only what it needs keeps working. */
export function clientService<K extends KindServiceKey>(
  client: SubmissionClient,
  key: K,
  portal: NonNullable<SubmissionClient[K]>,
): NonNullable<SubmissionClient[K]> {
  return extra(client, key) ?? portal;
}

/** `fetchBytes` for AttachmentPreviewModal: the portal's own reader, or the client's bytes route. */
export function useSubmissionFetchBytes(): (item: AttachmentPreviewItem) => Promise<Response> {
  const client = useSubmissionClient();
  if (client === (portalClient as SubmissionClient)) return portalFetchBytes;
  return (item) =>
    item.downloadUrl
      ? client.fetchPortalAttachmentBytes(item.downloadUrl)
      : Promise.reject(new Error('This attachment has no download route.'));
}
