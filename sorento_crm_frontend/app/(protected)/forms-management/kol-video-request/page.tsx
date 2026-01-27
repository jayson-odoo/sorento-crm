'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const statusLabels: Record<string, { label: string; variant: 'secondary' | 'warning' | 'success' }> = {
  draft: { label: 'Draft', variant: 'secondary' },
  pending: { label: 'Pending Approval', variant: 'warning' },
  approved: { label: 'Approved', variant: 'success' },
};

export default function KolVideoRequestPage() {
  const [status, setStatus] = useState<'draft' | 'pending' | 'approved'>('draft');

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>KOL Video Request Form</CardTitle>
          <Badge variant={statusLabels[status].variant} appearance="light">
            {statusLabels[status].label}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-medium">Salesman Name</label>
              <Input placeholder="Enter salesman name" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Dealer Details</label>
              <Input placeholder="Enter dealer details" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Company Name</label>
              <Input placeholder="Enter company name" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Location & Address</label>
              <Input placeholder="Enter location and address" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Event Period</label>
              <Input placeholder="YYYY-MM-DD to YYYY-MM-DD" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Sales Title</label>
              <Input placeholder="Enter sales title" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Video Posting Date</label>
              <Input type="date" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Sales Objective</label>
              <Select>
                <SelectTrigger>
                  <SelectValue placeholder="Select objective" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="clearance">Clearance</SelectItem>
                  <SelectItem value="roadshow">Roadshow</SelectItem>
                  <SelectItem value="grand-opening">Grand Opening</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Brands</label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {['Sorento', 'Cabana', 'Mocha', 'Born'].map((brand) => (
                <label key={brand} className="flex items-center gap-2 text-sm">
                  <Checkbox />
                  <span>{brand}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-medium">Influencers Qty</label>
              <Select>
                <SelectTrigger>
                  <SelectValue placeholder="Select quantity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 Pax</SelectItem>
                  <SelectItem value="2">2 Pax</SelectItem>
                  <SelectItem value="3">3 Pax</SelectItem>
                  <SelectItem value="4">4 Pax</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Target Audience</label>
              <Select>
                <SelectTrigger>
                  <SelectValue placeholder="Select audience" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="chinese">Chinese</SelectItem>
                  <SelectItem value="malay">Malay</SelectItem>
                  <SelectItem value="english">English</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Language</label>
              <Select>
                <SelectTrigger>
                  <SelectValue placeholder="Select language" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="english">English</SelectItem>
                  <SelectItem value="malay">Malay</SelectItem>
                  <SelectItem value="chinese">Chinese</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Promotion / Clearance Products</label>
            <Textarea placeholder="List products and prices" rows={4} />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Live Demo Products</label>
            <Textarea placeholder="List live demo items" rows={3} />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Lucky Draw / PWP Info</label>
            <Textarea placeholder="Describe lucky draw or PWP details" rows={3} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-medium">Approved By</label>
              <Input placeholder="Approver name" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Sales Manager</label>
              <Input placeholder="Manager name" />
            </div>
          </div>

          <div className="flex flex-wrap gap-3 justify-end">
            <Button variant="outline" onClick={() => setStatus('draft')}>
              Save Draft
            </Button>
            <Button variant="secondary" onClick={() => setStatus('pending')}>
              Submit for Approval
            </Button>
            <Button onClick={() => setStatus('approved')}>Approve</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
