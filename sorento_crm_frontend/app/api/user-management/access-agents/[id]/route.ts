import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma access agent to frontend expected format (snake_case)
 */
function transformAccessAgent(agent: {
  id: string;
  code: string;
  name: string;
  description: string | null;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
  syncedToExcel: boolean;
  lastSyncedToExcel: Date | null;
  picRespondUserId: string | null;
}) {
  return {
    id: agent.id,
    code: agent.code,
    name: agent.name,
    description: agent.description,
    is_active: agent.isActive,
    created_at: agent.createdAt,
    updated_at: agent.updatedAt,
    synced_to_excel: agent.syncedToExcel,
    last_synced_to_excel: agent.lastSyncedToExcel,
    pic_respond_user_id: agent.picRespondUserId,
  };
}

/**
 * Transform Prisma contact agent access to frontend expected format (snake_case)
 */
function transformContactAgentAccess(access: {
  id: string;
  respondContactId: string;
  agentId: string;
  isAllowed: boolean;
  validFrom: Date | null;
  validTo: Date | null;
  createdAt: Date;
  createdBy: string | null;
  syncedToExcel: boolean;
  lastSyncedToExcel: Date | null;
  updatedAt: Date | null;
}) {
  return {
    id: access.id,
    respond_contact_id: access.respondContactId,
    agent_id: access.agentId,
    is_allowed: access.isAllowed,
    valid_from: access.validFrom,
    valid_to: access.validTo,
    created_at: access.createdAt,
    created_by: access.createdBy,
    synced_to_excel: access.syncedToExcel,
    last_synced_to_excel: access.lastSyncedToExcel,
    updated_at: access.updatedAt,
  };
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid access agent ID format' },
        { status: 400 },
      );
    }

    const agent = await prisma.accessAgent.findUnique({
      where: { id },
      include: {
        contactAccesses: {
          orderBy: {
            createdAt: 'desc',
          },
        },
        _count: {
          select: {
            contactAccesses: true,
          },
        },
      },
    });

    if (!agent) {
      return NextResponse.json(
        { message: 'Access agent not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedAgent = {
      ...transformAccessAgent(agent),
      contact_accesses_count: agent._count?.contactAccesses || 0,
      contact_accesses: agent.contactAccesses.map(transformContactAgentAccess),
    };

    return NextResponse.json(transformedAgent);
  } catch (error) {
    console.error('Error fetching access agent:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid access agent ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const agent = await prisma.accessAgent.update({
      where: { id },
      data: {
        code: body.code,
        name: body.name,
        description: body.description || null,
        picRespondUserId: body.pic_respond_user_id || null,
        isActive: body.is_active !== false,
      },
    });

    // Transform to snake_case for frontend
    const transformedAgent = transformAccessAgent(agent);

    return NextResponse.json(transformedAgent);
  } catch (error) {
    console.error('Error updating access agent:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Access agent code already exists. Please use a different code.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid access agent ID format' },
        { status: 400 },
      );
    }

    // Check if agent exists
    const agent = await prisma.accessAgent.findUnique({
      where: { id },
    });

    if (!agent) {
      return NextResponse.json(
        { message: 'Access agent not found' },
        { status: 404 },
      );
    }

    // Permanently delete the access agent
    await prisma.accessAgent.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Access agent deleted successfully' });
  } catch (error) {
    console.error('Error deleting access agent:', error);
    
    // Handle foreign key constraint errors
    if (error instanceof Error && error.message.includes('Foreign key constraint')) {
      return NextResponse.json(
        { message: 'Cannot delete access agent. It is being used in contact access records.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
