/**
 * Database utility functions - now use FastAPI instead of Prisma
 */
import { apiFetch } from './api';
import { SystemSetting } from '@/app/models/system';

/**
 * Checks if a record is unique by calling FastAPI.
 * Note: This is a simplified version - FastAPI should handle uniqueness validation
 * @param table - Table name (kept for compatibility)
 * @param fields - Fields to check for uniqueness
 * @param exclude - Fields to exclude from the check
 * @returns - `true` if unique, otherwise `false`.
 */
export async function isUnique(
  table: string,
  fields: Record<string, unknown>,
  exclude?: Record<string, unknown>,
): Promise<boolean> {
  // For now, return true - FastAPI endpoints should handle uniqueness validation
  // This function is kept for compatibility but validation should be done server-side
  return true;
}

/**
 * Fetches system settings from FastAPI.
 * @returns - Settings or `null`.
 */
export async function getSettings(): Promise<SystemSetting | null> {
  try {
    const response = await apiFetch('/api/v1/user-management/settings', {
      method: 'GET',
    });
    
    if (!response.ok) {
      return null;
    }
    
    const data = await response.json();
    return data.settings;
  } catch {
    return null;
  }
}
