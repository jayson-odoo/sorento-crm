import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { AttachmentResponse } from '../types/attachment.types';

/**
 * driveService - the Unified Drive listing for Resource Management → Files.
 *
 * Backend contract (LIVE - see docs/plans/PLAN-unified-drive-files.md, D11):
 *   GET /api/v1/resource-management/attachments/drive
 *     query:
 *       directory_id   omit = drive root; else the folder to list
 *       recursive      bool; auto-forced true by the backend when `query` is non-empty
 *       query          search term - matches file names AND folder names
 *       sort           name (default, interleaves folders+files)
 *                      | type | size | modified | uploaded_by | attachment_type | created_at
 *                        (non-name sorts push folders to the end)
 *       dir            asc | desc (default asc)
 *       page           >= 1 (default 1)
 *       limit          default 50
 *       + the file filters: attachment_type_id, attachment_type_code, uploaded_by,
 *         uploaded_at_from, uploaded_at_to, access_levels (repeated) + access_levels_match,
 *         link_status, storage_status, direct_access_only, is_deleted (Trash)
 *     200 -> {
 *       data: DriveItem[]                       // discriminated by `kind`
 *       pagination: { total, page, limit }
 *       empty: boolean
 *       recursive: boolean                       // the scope the backend actually used
 *     }
 *
 *   folder row: { kind:'folder', id, name, parent_id, sort_order, created_at, directory_path }
 *               directory_path = the folder's PARENT path (its Location).
 *   file row:   AttachmentResponse fields + { kind:'file', directory_path, uploaded_by_user }
 *               directory_path = containing-folder path, e.g. "Marketing / Campaigns".
 *
 * Browse (empty query, no file filter) returns immediate children only and includes
 * folders. A non-empty query OR any active file filter switches the backend to a
 * recursive subtree scan and excludes folders.
 */

export interface DriveFolderItem {
  kind: 'folder';
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number | null;
  created_at?: string | null;
  /** Parent path of this folder (its Location). Null/empty at root. */
  directory_path?: string | null;
  /** Owning company. Null means the folder is shared across every company. */
  company_id?: string | null;
  company_name?: string | null;
}

export interface DriveFileItem extends AttachmentResponse {
  kind: 'file';
  /** Containing-folder path, e.g. "Marketing / Campaigns". */
  directory_path?: string | null;
  uploaded_by_user?: {
    id: string;
    name: string;
    email: string;
  } | null;
}

export type DriveItem = DriveFolderItem | DriveFileItem;

export function isFolderItem(item: DriveItem): item is DriveFolderItem {
  return item.kind === 'folder';
}

export function isFileItem(item: DriveItem): item is DriveFileItem {
  return item.kind === 'file';
}

export interface DriveListResponse {
  data: DriveItem[];
  pagination: { total: number; page: number; limit?: number };
  empty: boolean;
  recursive: boolean;
}

export interface DriveListParams {
  pageIndex: number;
  pageSize: number;
  /** Single-sort, matching the DataGrid contract. `id` maps to the `sort` enum. */
  sorting?: { id: string; desc: boolean }[];
  /** Search term. Non-empty -> recursive scope (folders excluded). */
  searchQuery?: string;
  /** null/undefined = drive root. */
  directory_id?: string | null;
  /** Force recursive even with an empty query (the inverse of "this folder only"). */
  recursive?: boolean;
  is_deleted?: boolean;
  attachment_type_id?: string;
  attachment_type_code?: string;
  uploaded_by?: string;
  uploaded_at_from?: string;
  uploaded_at_to?: string;
  access_levels?: string[];
  access_levels_match?: 'any' | 'all' | 'exact';
  link_status?: 'linked' | 'unlinked';
  storage_status?: 'accessible' | 'missing' | 'unchecked';
  direct_access_only?: boolean;
  /** A company id, `shared`, or omitted for today's `IS NULL OR IN (scope)` result. */
  company?: string;
}

export async function getDriveContents(params: DriveListParams): Promise<DriveListResponse> {
  const sp = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      sorting: params.sorting,
      searchQuery: params.searchQuery,
    },
    {
      directory_id:
        params.directory_id != null && params.directory_id !== ''
          ? params.directory_id
          : undefined,
      recursive: params.recursive ? 'true' : undefined,
      is_deleted: params.is_deleted !== undefined ? String(params.is_deleted) : undefined,
      attachment_type_id: params.attachment_type_id,
      attachment_type_code: params.attachment_type_code,
      uploaded_by: params.uploaded_by?.trim() || undefined,
      uploaded_at_from: params.uploaded_at_from || undefined,
      uploaded_at_to: params.uploaded_at_to || undefined,
      access_levels_match:
        params.access_levels && params.access_levels.length > 0
          ? params.access_levels_match
          : undefined,
      link_status: params.link_status,
      storage_status: params.storage_status,
      direct_access_only: params.direct_access_only ? 'true' : undefined,
      company: params.company,
    }
  );
  if (params.access_levels && params.access_levels.length > 0) {
    for (const lvl of params.access_levels) {
      if (lvl) sp.append('access_levels', lvl);
    }
  }

  const response = await apiFetch(
    `/api/v1/resource-management/attachments/drive?${sp.toString()}`
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load drive contents'));
  }
  return response.json();
}
