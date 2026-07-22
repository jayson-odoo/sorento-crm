'use client';

import { useState } from 'react';
import { SquarePlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';

const InvitePeople = () => {
  const [invitepeopleInput, setInvitePeopleInput] = useState('jason@studio.io');
  const [role, setRole] = useState('1');
  return (
    <Card>
      <CardHeader id="webhooks">
        <CardTitle>Invite People</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="flex items-center flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-32">Email</Label>
          <div className="grow min-w-48">
            <Input
              className="w-full"
              type="text"
              value={invitepeopleInput}
              onChange={(e) => setInvitePeopleInput(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-baseline flex-wrap gap-2.5">
          <Label className="flex w-full max-w-32">Role</Label>
          <div className="grid gap-5 grow items-start">
            <SearchableSelect
              value={role}
              onChange={setRole}
              placeholder="Select"
              triggerClassName="w-full"
              options={[
                { value: '1', label: 'Member' },
                { value: '2', label: 'Option 2' },
                { value: '3', label: 'Option 3' },
              ]}
            />
            <div>
              <Button variant="outline">
                <SquarePlus size={16} /> Add more
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
      <CardFooter className="justify-center">
        <Button>Invite People</Button>
      </CardFooter>
    </Card>
  );
};

export { InvitePeople };
