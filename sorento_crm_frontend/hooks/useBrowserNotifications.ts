'use client';

import { useCallback, useEffect, useState } from 'react';

export type NotificationPermission = 'granted' | 'denied' | 'default';

export function useBrowserNotifications() {
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const [isSupported, setIsSupported] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const supported = 'Notification' in window && 'requestPermission' in Notification;
    setIsSupported(supported);
    if (supported) {
      setPermission(Notification.permission as NotificationPermission);
    }
  }, []);

  const requestPermission = useCallback((): Promise<NotificationPermission> => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      return Promise.resolve('denied');
    }
    return Notification.requestPermission().then((result) => {
      setPermission(result as NotificationPermission);
      return result as NotificationPermission;
    });
  }, []);

  const showNotification = useCallback(
    (title: string, options?: { body?: string; tag?: string; icon?: string }) => {
      if (typeof window === 'undefined' || !('Notification' in window)) return null;
      if (Notification.permission !== 'granted') return null;
      const n = new Notification(title, {
        body: options?.body,
        tag: options?.tag ?? 'sorento-notification',
        icon: options?.icon ?? '/media/app/mini-logo.svg',
      });
      n.onclick = () => {
        window.focus();
        n.close();
      };
      return n;
    },
    [],
  );

  return { permission, isSupported, requestPermission, showNotification };
}
