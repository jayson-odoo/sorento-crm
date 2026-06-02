/**
 * Stable React Query keys for the Upload Activity feature.
 * Lives in its own module so both the hook and the manager can import
 * without forming a cycle.
 */

export const UPLOAD_ACTIVITY_QUERY_KEY = ['upload-activity', 'me'] as const;
