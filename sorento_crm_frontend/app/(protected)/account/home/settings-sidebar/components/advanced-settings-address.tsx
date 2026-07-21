'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';

const AdvancedSettingsAddress = () => {
  const [address, setAddress] = useState('');
  const [country, setCountry] = useState('1');
  const [state, setState] = useState('');
  const [city, setCity] = useState('');
  const [postcode, setPostcode] = useState('');

  return (
    <Card>
      <CardHeader id="advanced_settings_address">
        <CardTitle>Address</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5 lg:py-7.5">
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full items-center gap-1 max-w-56">
            Address
          </Label>
          <Input
            id="address"
            type="text"
            placeholder="Avinguda Imaginària, 789"
            defaultValue={address}
            onChange={(e) => setAddress(e.target.value)}
          />
        </div>
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Country</Label>
          <div className="grow">
            <SearchableSelect
              value={country}
              onChange={setCountry}
              placeholder="Select"
              triggerClassName="w-full"
              options={[
                { value: '1', label: 'Spain' },
                { value: '2', label: 'Option 2' },
                { value: '3', label: 'Option 3' },
              ]}
            />
          </div>
        </div>
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">State</Label>
          <Input
            id="state"
            type="text"
            placeholder="State"
            defaultValue={state}
            onChange={(e) => setState(e.target.value)}
          />
        </div>
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">City</Label>
          <Input
            id="city"
            type="text"
            placeholder="Barcelona"
            defaultValue={city}
            onChange={(e) => setCity(e.target.value)}
          />
        </div>
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Postcode</Label>
          <Input
            id="postcode"
            type="text"
            placeholder="08012"
            defaultValue={postcode}
            onChange={(e) => setPostcode(e.target.value)}
          />
        </div>
        <div className="flex justify-end pt-2.5">
          <Button>Save Changes</Button>
        </div>
      </CardContent>
    </Card>
  );
};

export { AdvancedSettingsAddress };
