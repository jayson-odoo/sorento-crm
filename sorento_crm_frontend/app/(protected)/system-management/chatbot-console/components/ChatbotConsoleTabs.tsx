'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import AgentConsole from './AgentConsole';
import ChatbotConsole from './ChatbotConsole';

export default function ChatbotConsoleTabs() {
  return (
    <Tabs defaultValue="bot">
      <TabsList variant="line" className="mb-4">
        <TabsTrigger value="bot">Bot</TabsTrigger>
        <TabsTrigger value="agent">Agent</TabsTrigger>
      </TabsList>
      <TabsContent value="bot">
        <ChatbotConsole />
      </TabsContent>
      <TabsContent value="agent">
        <AgentConsole />
      </TabsContent>
    </Tabs>
  );
}
