'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Switch } from '@/components/ui/switch';

const Webhooks = () => {
  const [webhooknameInput, setWebhookNameInput] = useState('CostaRicaHook');
  const [eventType, setEventType] = useState('1');

  return (
    <Card className="pb-2.5">
      <CardHeader id="webhooks">
        <CardTitle>Webhooks</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5">
        <p className="text-sm text-foreground">
          Set up Webhooks to trigger actions on external services in real-time.
          Stay informed on updates and changes to ensure seamless integration.
        </p>
        <div className="flex items-center flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Webhook URL</Label>
          <div className="grow">
            <Input type="text" placeholder="Enter URL" />
          </div>
        </div>
        <div className="flex items-center flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Webhook Name</Label>
          <div className="grow">
            <Input
              type="text"
              value={webhooknameInput}
              onChange={(e) => setWebhookNameInput(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Event Type</Label>
          <div className="grow">
            <SearchableSelect
              value={eventType}
              onChange={setEventType}
              placeholder="Select"
              triggerClassName="w-full"
              options={[
                { value: '1', label: 'All Events' },
                { value: '2', label: 'Push Webhooks' },
                { value: '3', label: 'Pipe Webhook' },
                { value: '4', label: 'Plugin Webhooks' },
              ]}
            />
          </div>
        </div>
        <div className="flex items-center flex-wrap lg:flex-nowrap gap-2.5 mb-2.5">
          <Label className="flex w-full max-w-56">Custom Headers</Label>
          <div className="grow">
            <div className="flex items-center space-x-2">
              <Label htmlFor="size-sm" className="text-sm">
                Use Custom Header
              </Label>
              <Switch id="size-sm" size="sm" defaultChecked />
            </div>
          </div>
        </div>
        <div className="flex justify-end">
          <Button>Save Changes</Button>
        </div>
      </CardContent>
    </Card>
  );
};

export { Webhooks };
