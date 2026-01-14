import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma contact agent access to frontend expected format (snake_case)
 */
function transformContactAgentAccess(access: any) {
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

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; contactId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id, contactId } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id) || !uuidRegex.test(contactId)) {
      return NextResponse.json(
        { message: 'Invalid ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const contactAccess = await prisma.contactAgentAccess.update({
      where: { id: contactId },
      data: {
        respondContactId: body.respond_contact_id,
        isAllowed: body.is_allowed !== false,
        validFrom: body.valid_from ? new Date(body.valid_from) : null,
        validTo: body.valid_to ? new Date(body.valid_to) : null,
      },
    });

    // Transform to snake_case for frontend
    const transformedContactAccess = transformContactAgentAccess(contactAccess);

    return NextResponse.json(transformedContactAccess);
  } catch (error) {
    console.error('Error updating contact access agent:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Contact access already exists for this agent and contact ID.' },
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
  { params }: { params: Promise<{ id: string; contactId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id, contactId } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id) || !uuidRegex.test(contactId)) {
      return NextResponse.json(
        { message: 'Invalid ID format' },
        { status: 400 },
      );
    }

    // Check if contact access exists
    const contactAccess = await prisma.contactAgentAccess.findUnique({
      where: { id: contactId },
    });

    if (!contactAccess) {
      return NextResponse.json(
        { message: 'Contact access agent not found' },
        { status: 404 },
      );
    }

    // Verify it belongs to the agent
    if (contactAccess.agentId !== id) {
      return NextResponse.json(
        { message: 'Contact access does not belong to this agent' },
        { status: 400 },
      );
    }

    // Permanently delete the contact access
    await prisma.contactAgentAccess.delete({
      where: { id: contactId },
    });

    return NextResponse.json({ message: 'Contact access agent deleted successfully' });
  } catch (error) {
    console.error('Error deleting contact access agent:', error);

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
