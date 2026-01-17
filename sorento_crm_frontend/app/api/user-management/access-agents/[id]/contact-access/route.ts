import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

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

    const contactAccesses = await prisma.contactAgentAccess.findMany({
      where: { agentId: id },
      orderBy: {
        createdAt: 'desc',
      },
    });

    // Transform to snake_case for frontend
    const transformedContactAccesses = contactAccesses.map(transformContactAgentAccess);

    return NextResponse.json(transformedContactAccesses);
  } catch (error) {
    console.error('Error fetching contact access agents:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function POST(
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

    const contactAccess = await prisma.contactAgentAccess.create({
      data: {
        respondContactId: body.respond_contact_id,
        agentId: id,
        isAllowed: body.is_allowed !== false,
        validFrom: body.valid_from ? new Date(body.valid_from) : null,
        validTo: body.valid_to ? new Date(body.valid_to) : null,
        createdBy: session.user?.id || null,
      },
    });

    // Transform to snake_case for frontend
    const transformedContactAccess = transformContactAgentAccess(contactAccess);

    return NextResponse.json(transformedContactAccess, { status: 201 });
  } catch (error) {
    console.error('Error creating contact access agent:', error);
    
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
