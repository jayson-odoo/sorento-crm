'use client';

import { useState } from 'react';
import Link from 'next/link';
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
  const [emailInput, setEmailInput] = useState('jason@studio.io');
  const [role, setRole] = useState('1');
  return (
    <Card>
      <CardHeader>
        <CardTitle>Invite People</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-32">Email</Label>
          <Input
            type="text"
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
          />
        </div>
        <div className="flex items-baseline flex-wrap gap-2.5">
          <Label className="flex w-full max-w-32">Role</Label>
          <div className="flex flex-col items-start grow gap-5">
            <SearchableSelect
              value={role}
              onChange={setRole}
              placeholder="Select"
              triggerClassName="w-full"
              options={[
                { value: '1', label: 'Member' },
                { value: '2', label: 'Editor' },
                { value: '3', label: 'Designer' },
                { value: '4', label: 'Admin' },
              ]}
            />
            <Button variant="outline">
              <SquarePlus size={12} />
              Add more
            </Button>
          </div>
        </div>
      </CardContent>
      <CardFooter className="justify-center">
        <Button>
          <Link href="#">Invite People</Link>
        </Button>
      </CardFooter>
    </Card>
  );
};

export { InvitePeople };
