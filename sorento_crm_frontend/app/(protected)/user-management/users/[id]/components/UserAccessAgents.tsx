'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import UserAgentAccessDialog from './UserAgentAccessDialog';

interface UserAccessAgentsProps {
  userId: string;
}

interface AccessAgent {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
}

export default function UserAccessAgents({ userId }: UserAccessAgentsProps) {
  const queryClient = useQueryClient();
  const [selectedAgent, setSelectedAgent] = useState<{ id: string; name: string } | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  // Fetch all access agents
  const { data: agentsData, isLoading: agentsLoading } = useQuery({
    queryKey: ['access-agents', 'all'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/access-agents?page=1&limit=1000');
      if (!response.ok) throw new Error('Failed to fetch access agents');
      return response.json();
    },
  });

  // Fetch user's current agent accesses
  const { data: userAgentsData, isLoading: userAgentsLoading } = useQuery({
    queryKey: ['user-agent-accesses', userId],
    queryFn: async () => {
      // This endpoint doesn't exist yet, we'll need to create it
      // For now, return empty array
      return { data: [] };
    },
  });

  const handleAddAgent = (agent: AccessAgent) => {
    setSelectedAgent({ id: agent.id, name: agent.name });
    setDialogOpen(true);
  };

  const agents = agentsData?.data || [];
  const userAgents = userAgentsData?.data || [];

  // Filter out agents that are already assigned
  const availableAgents = agents.filter(
    (agent: AccessAgent) => !userAgents.some((ua: any) => ua.agent_id === agent.id)
  );

  if (agentsLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Access Agents</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Access Agents</CardTitle>
        </CardHeader>
        <CardContent>
          {availableAgents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No available access agents to add.</p>
          ) : (
            <div className="space-y-2">
              {availableAgents.map((agent: AccessAgent) => (
                <div
                  key={agent.id}
                  className="flex items-center justify-between p-3 border rounded-lg"
                >
                  <div>
                    <div className="font-medium">{agent.name}</div>
                    <div className="text-sm text-muted-foreground">{agent.code}</div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleAddAgent(agent)}
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Add
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {selectedAgent && (
        <UserAgentAccessDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          userId={userId}
          agentId={selectedAgent.id}
          agentName={selectedAgent.name}
        />
      )}
    </>
  );
}
