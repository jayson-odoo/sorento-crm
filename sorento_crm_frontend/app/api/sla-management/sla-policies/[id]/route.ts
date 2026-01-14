import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma SLA policy to frontend expected format (snake_case)
 */
function transformSLAPolicy(policy: any) {
  return {
    id: policy.id,
    code: policy.code,
    name: policy.name,
    description: policy.description,
    is_active: policy.isActive,
    created_at: policy.createdAt,
    updated_at: policy.updatedAt,
  };
}

/**
 * Transform Prisma SLA policy tier to frontend expected format (snake_case)
 */
function transformSLAPolicyTier(tier: any) {
  return {
    id: tier.id,
    policy_id: tier.policyId,
    tier_level: tier.tierLevel,
    tier_name: tier.tierName,
    response_hours: tier.responseHours,
    created_at: tier.createdAt,
    updated_at: tier.updatedAt,
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
        { message: 'Invalid SLA policy ID format' },
        { status: 400 },
      );
    }

    const policy = await prisma.sLAPolicy.findUnique({
      where: { id },
      include: {
        tiers: {
          orderBy: {
            tierLevel: 'asc',
          },
        },
        _count: {
          select: {
            tiers: true,
            tracking: true,
          },
        },
      },
    });

    if (!policy) {
      return NextResponse.json(
        { message: 'SLA policy not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedPolicy = {
      ...transformSLAPolicy(policy),
      tiers_count: policy._count?.tiers || 0,
      tracking_count: policy._count?.tracking || 0,
      tiers: policy.tiers.map(transformSLAPolicyTier),
    };

    return NextResponse.json(transformedPolicy);
  } catch (error) {
    console.error('Error fetching SLA policy:', error);
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
        { message: 'Invalid SLA policy ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const policy = await prisma.sLAPolicy.update({
      where: { id },
      data: {
        code: body.code,
        name: body.name,
        description: body.description || null,
        isActive: body.is_active !== false,
      },
    });

    // Transform to snake_case for frontend
    const transformedPolicy = transformSLAPolicy(policy);

    return NextResponse.json(transformedPolicy);
  } catch (error) {
    console.error('Error updating SLA policy:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'SLA policy code already exists. Please use a different code.' },
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
        { message: 'Invalid SLA policy ID format' },
        { status: 400 },
      );
    }

    // Check if policy exists
    const policy = await prisma.sLAPolicy.findUnique({
      where: { id },
    });

    if (!policy) {
      return NextResponse.json(
        { message: 'SLA policy not found' },
        { status: 404 },
      );
    }

    // Permanently delete the SLA policy (cascade will delete tiers)
    await prisma.sLAPolicy.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'SLA policy deleted successfully' });
  } catch (error) {
    console.error('Error deleting SLA policy:', error);
    
    // Handle foreign key constraint errors
    if (error instanceof Error && error.message.includes('Foreign key constraint')) {
      return NextResponse.json(
        { message: 'Cannot delete SLA policy. It is being used in conversation SLA tracking.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
