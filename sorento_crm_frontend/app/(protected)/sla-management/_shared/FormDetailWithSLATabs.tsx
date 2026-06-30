'use client';

import { ReactNode } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import FormSLATrackingTab from './FormSLATrackingTab';
import type { FormSLASourceType } from './formSLAService';

export interface FormDetailExtraTab {
  value: string;
  label: string;
  content: ReactNode;
}

interface FormDetailWithSLATabsProps {
  sourceEntityType: FormSLASourceType;
  sourceEntityId: string;
  children: ReactNode;
  /** Entity-specific tabs inserted between "Details" and "SLA Tracking". */
  extraTabs?: FormDetailExtraTab[];
}

export default function FormDetailWithSLATabs({
  sourceEntityType,
  sourceEntityId,
  children,
  extraTabs = [],
}: FormDetailWithSLATabsProps) {
  return (
    <Tabs defaultValue="details" className="space-y-4">
      <TabsList>
        <TabsTrigger value="details">Details</TabsTrigger>
        {extraTabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value}>
            {tab.label}
          </TabsTrigger>
        ))}
        <TabsTrigger value="sla">SLA Tracking</TabsTrigger>
      </TabsList>
      <TabsContent value="details" className="m-0">
        {children}
      </TabsContent>
      {extraTabs.map((tab) => (
        <TabsContent key={tab.value} value={tab.value} className="m-0">
          {tab.content}
        </TabsContent>
      ))}
      <TabsContent value="sla" className="m-0">
        <FormSLATrackingTab
          sourceEntityType={sourceEntityType}
          sourceEntityId={sourceEntityId}
        />
      </TabsContent>
    </Tabs>
  );
}
