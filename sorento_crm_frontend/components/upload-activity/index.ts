/**
 * Upload Activity drawer - public exports.
 *
 * Phase 1: mocks-driven prototype. Phase 2 will keep these import
 * sites stable and only swap internals.
 */

export { UploadActivityDrawer } from './UploadActivityDrawer';
export { UploadActivityIcon } from './UploadActivityIcon';
export { IntegrationCard } from './IntegrationCard';
export { IntegrationPanel } from './IntegrationPanel';
export { IntegrationStatusChip } from './IntegrationStatusChip';
export {
  UploadManagerProvider,
  useUploadManager,
  useOptimisticSessions,
} from './UploadManagerContext';
export { useUploadActivity } from './useUploadActivity';
export { useImportJobDrawer } from './useImportJobDrawer';
export { UPLOAD_ACTIVITY_QUERY_KEY } from './queryKeys';
export { useAttachmentIntegrationLog } from './useAttachmentIntegrationLog';
export type {
  FileStatus,
  LinkedEntity,
  SessionStatus,
  SessionType,
  UnlinkedReason,
  UploadActivityFile,
  UploadActivitySession,
} from './types';
