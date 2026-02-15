import { Metadata } from 'next';
import Link from 'next/link';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { Button } from '@/components/ui/button';
import { ChevronLeft } from 'lucide-react';
import TeamMembersClient from './components/team-members-client';

export const metadata: Metadata = {
  title: 'Team members',
  description: 'Manage team members for round-robin.',
};

type Props = { params: Promise<{ id: string }> };

export default async function TeamMembersPage({ params }: Props) {
  const { id } = await params;
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Team members</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/user-management/users">User Management</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/user-management/teams">Teams</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Members</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button variant="outline" size="sm" asChild>
              <Link href="/user-management/teams">
                <ChevronLeft className="me-1 size-4" />
                Back to teams
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>
      <Container>
        <TeamMembersClient teamId={id} />
      </Container>
    </>
  );
}
