'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';

export const Packaging = () => {
  const [packageName, setPackageName] = useState('Mike Anderson - Medium Box');
  const [totalWeight, setTotalWeight] = useState('2.1');
  const [length, setLength] = useState('48');
  const [width, setWidth] = useState('36');
  const [height, setHeight] = useState('20');
  const [packageType, setPackageType] = useState('1');
  const [unit, setUnit] = useState('1');

  return (
    <Card className="overflow-hidden">
      <CardHeader className="bg-muted/50 px-5">
        <CardTitle>Packaging</CardTitle>
      </CardHeader>

      <CardContent className="px-5">
        <div className="space-y-4.5">
          {/* Package Name */}
          <div className="flex flex-col gap-2 w-full">
            <span className="text-xs text-mono font-medium">Package Name</span>
            <Input
              className=""
              type="text"
              value={packageName}
              onChange={(e) => setPackageName(e.target.value)}
            />
          </div>

          <div className="grid sm:grid-cols-2 gap-5">
            <div className="flex flex-col gap-2 w-full">
              <span className="form-info text-xs text-mono font-medium">
                Package Type
              </span>

              <SearchableSelect
                value={packageType}
                onChange={setPackageType}
                placeholder=""
                triggerClassName="w-full"
                options={[
                  { value: '1', label: 'Medium Box' },
                  { value: '2', label: 'Small Box' },
                  { value: '3', label: 'Large Box' },
                ]}
              />
            </div>

            <div className="flex flex-col gap-2 w-full">
              <span className="form-info text-xs text-mono font-medium">
                Total Weight
              </span>

              <Input
                placeholder=""
                type="text"
                value={totalWeight}
                onChange={(e) => setTotalWeight(e.target.value)}
                className="w-full"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-5">
            <div className="flex-1 min-w-[100px]">
              <div className="flex flex-col gap-2 w-full">
                <span className="text-xs text-mono font-medium">Length</span>

                <Input
                  placeholder=""
                  type="text"
                  value={length}
                  onChange={(e) => setLength(e.target.value)}
                  className="w-full"
                />
              </div>
            </div>

            <div className="flex-1 min-w-[100px]">
              <div className="flex flex-col gap-2 w-full">
                <span className="text-xs text-mono font-medium">Width</span>

                <Input
                  placeholder=""
                  type="text"
                  value={width}
                  onChange={(e) => setWidth(e.target.value)}
                  className="w-full"
                />
              </div>
            </div>

            <div className="flex-1 min-w-[100px]">
              <div className="flex flex-col gap-2 w-full">
                <span className="text-xs text-mono font-medium">Height</span>

                <Input
                  placeholder=""
                  type="text"
                  value={height}
                  onChange={(e) => setHeight(e.target.value)}
                  className="w-full"
                />
              </div>
            </div>

            <div className="w-auto min-w-[66px]">
              <SearchableSelect
                value={unit}
                onChange={setUnit}
                placeholder=""
                triggerClassName="w-full"
                options={[
                  { value: '1', label: 'sm' },
                  { value: '2', label: 'mm' },
                  { value: '3', label: 'dm' },
                ]}
              />
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox defaultChecked />
            <Label>Save package for future orders</Label>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
