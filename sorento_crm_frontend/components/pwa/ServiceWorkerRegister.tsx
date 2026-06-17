'use client';

import { useEffect } from 'react';

/**
 * Registers the PWA service worker (TCK-33). Scope + script path honour
 * NEXT_PUBLIC_BASE_PATH so the worker controls the app under a sub-path deploy.
 * Renders nothing.
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    const base = process.env.NEXT_PUBLIC_BASE_PATH || '';
    const swUrl = `${base}/sw.js`;
    navigator.serviceWorker.register(swUrl, { scope: `${base}/` }).catch(() => {
      // registration failures are non-fatal (e.g. unsupported / insecure context)
    });
  }, []);
  return null;
}
