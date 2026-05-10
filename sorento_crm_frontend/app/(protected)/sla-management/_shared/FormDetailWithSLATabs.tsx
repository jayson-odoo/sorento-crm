'use client';

import { ReactNode } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import FormSLATrackingTab from './FormSLATrackingTab';
import type { FormSLASourceType } from './formSLAService';

interface FormDetailWithSLATabsProps {
  sourceEntityType: FormSLASourceType;
  sourceEntityId: string;
  children: ReactNode;
}

export default function FormDetailWithSLATabs({
  sourceEntityType,
  sourceEntityId,
  children,
}: FormDetailWithSLATabsProps) {
  return (
    <Tabs defaultValue="details" className="space-y-4">
      <TabsList>
        <TabsTrigger value="details">Details</TabsTrigger>
        <TabsTrigger value="sla">SLA Tracking</TabsTrigger>
      </TabsList>
      <TabsContent value="details" className="m-0">
        {children}
      </TabsContent>
      <TabsContent value="sla" className="m-0">
        <FormSLATrackingTab
          sourceEntityType={sourceEntityType}
          sourceEntityId={sourceEntityId}
        />
      </TabsContent>
    </Tabs>
  );
}
