/**
 * System log service - now calls FastAPI instead of Prisma
 * Works in both client and server contexts
 */
export interface SystemLogProps {
  event: string;
  userId: string;
  entityId?: string;
  entityType?: string;
  description?: string;
  ipAddress?: string;
  meta?: string;
}

export async function systemLog(
  {
    event,
    userId,
    entityId,
    entityType,
    description,
    ipAddress,
    meta,
  }: SystemLogProps,
  tx?: any, // Transaction parameter kept for compatibility but not used
) {
  try {
    // Determine if we're in server or client context
    const isServer = typeof window === 'undefined';
    const apiUrl =
      process.env.FASTAPI_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? '';
    if (isServer && !apiUrl) {
      console.error('[LOG] FASTAPI_INTERNAL_URL / NEXT_PUBLIC_API_URL not set; cannot post system log from server context');
      return;
    }

    // Build the URL
    let url = '/api/v1/user-management/system-logs';
    if (isServer && apiUrl) {
      url = `${apiUrl}${url}`;
    }
    
    // For server-side, use native fetch
    // For client-side, this would typically use apiFetch, but we'll use fetch for simplicity
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event,
        user_id: userId,
        entity_id: entityId,
        entity_type: entityType,
        description,
        ip_address: ipAddress,
        meta,
      }),
    });
    
    if (!response.ok) {
      console.error('[LOG] Failed to create system log:', response.status, await response.text().catch(() => ''));
    }
  } catch (error) {
    console.error('[LOG] Failed to log activity:', error);
  }
}
