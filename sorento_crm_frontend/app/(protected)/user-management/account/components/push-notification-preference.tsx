'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  isPushSupported,
  getPushState,
  subscribeToPush,
  unsubscribeFromPush,
} from '@/services/pushService';
import { describePushFailure } from '@/lib/pushFailureMessage';

/** Browser push notification opt-in (TCK-33). The subscription is the opt-in;
 *  no separate server pref. */
export default function PushNotificationPreference() {
  const [supported, setSupported] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSupported(isPushSupported());
    void getPushState().then(setEnabled);
  }, []);

  const onEnable = async () => {
    setBusy(true);
    try {
      const result = await subscribeToPush();
      setEnabled(result.ok);
      if (result.ok) {
        toast.success('Notifications enabled');
        return;
      }
      // Why it failed decides what the user has to go and do about it.
      const { title, description } = describePushFailure(result.reason);
      toast.error(title, description ? { description } : undefined);
    } finally {
      setBusy(false);
    }
  };

  const onDisable = async () => {
    setBusy(true);
    try {
      await unsubscribeFromPush();
      setEnabled(false);
      toast.success('Notifications disabled');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="py-4">
        <CardTitle>Browser Notifications</CardTitle>
      </CardHeader>
      <CardContent className="py-4">
        {!supported ? (
          <p className="text-sm text-muted-foreground">
            This browser does not support push notifications. On iOS, add the app
            to your home screen first (iOS 16.4+).
          </p>
        ) : (
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              Get alerts on this device even when the app is closed.
            </p>
            {enabled ? (
              <Button variant="outline" onClick={onDisable} disabled={busy}>
                Disable
              </Button>
            ) : (
              <Button onClick={onEnable} disabled={busy}>
                Enable notifications
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
