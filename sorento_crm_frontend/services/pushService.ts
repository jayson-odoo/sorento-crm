import { apiFetch } from '@/lib/api';

/** Web push subscribe/unsubscribe (TCK-33). The browser subscription IS the
 *  opt-in; the backend mirrors in-app notifications to web_push for subscribed
 *  users. `subscribeToPush` never throws: every way an enable attempt can fail
 *  comes back as a named reason the caller can turn into guidance. */

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    typeof Notification !== 'undefined'
  );
}

export async function getPushState(): Promise<boolean> {
  if (!isPushSupported()) return false;
  try {
    const reg = await navigator.serviceWorker.ready;
    return !!(await reg.pushManager.getSubscription());
  } catch {
    return false;
  }
}

/** Why an enable attempt did not end in a stored subscription. The caller maps
 *  each reason to the guidance that actually unblocks it. */
export type PushSubscribeFailure =
  | 'unsupported'
  | 'no-key'
  | 'permission-denied'
  | 'push-service-blocked'
  | 'subscribe-failed'
  | 'save-failed';

export type PushSubscribeResult = { ok: true } | { ok: false; reason: PushSubscribeFailure };

/**
 * A rejection from `pushManager.subscribe`, named.
 *
 * Brave (and any browser cut off from its push service by a VPN, a firewall or
 * an ad blocker) rejects with `AbortError: Registration failed - push service
 * error`. That is fixable by the user, but only if we say so, so it is kept
 * apart from a genuine failure.
 */
function classifySubscribeError(error: unknown): PushSubscribeFailure {
  const name = (error as { name?: string } | null)?.name ?? '';
  const message = String((error as { message?: string } | null)?.message ?? '');
  if (name === 'NotAllowedError') return 'permission-denied';
  if (name === 'AbortError' || /push service/i.test(message)) return 'push-service-blocked';
  return 'subscribe-failed';
}

export async function subscribeToPush(): Promise<PushSubscribeResult> {
  if (!isPushSupported()) return { ok: false, reason: 'unsupported' };
  const vapid = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  if (!vapid) return { ok: false, reason: 'no-key' };

  let sub: PushSubscription;
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') return { ok: false, reason: 'permission-denied' };
    const reg = await navigator.serviceWorker.ready;
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapid) as unknown as BufferSource,
    });
  } catch (error) {
    return { ok: false, reason: classifySubscribeError(error) };
  }

  try {
    const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
    const res = await apiFetch('/api/v1/notifications/push/subscriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
    });
    return res.ok ? { ok: true } : { ok: false, reason: 'save-failed' };
  } catch {
    return { ok: false, reason: 'save-failed' };
  }
}

export async function unsubscribeFromPush(): Promise<boolean> {
  if (!isPushSupported()) return false;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (!sub) return true;
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    await apiFetch(
      `/api/v1/notifications/push/subscriptions?endpoint=${encodeURIComponent(endpoint)}`,
      { method: 'DELETE' },
    );
    return true;
  } catch {
    return false;
  }
}
