import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { searchParams } = new URL(req.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '50', 10);

    const totalCount = await prisma.form.count();

    const forms = await prisma.form.findMany({
      skip: (page - 1) * limit,
      take: limit,
      orderBy: {
        updatedAt: 'desc',
      },
    });

    // Transform to snake_case for frontend
    const transformedForms = forms.map((f: { id: string; code: string; name: string; purpose: string | null; language: string; version: number; isActive: boolean; createdAt: Date; updatedAt: Date; attachmentId: string | null; createdBy: string | null }) => ({
      id: f.id,
      code: f.code,
      name: f.name,
      purpose: f.purpose,
      language: f.language,
      version: f.version,
      is_active: f.isActive,
      attachment_id: f.attachmentId,
      created_by: f.createdBy,
      created_at: f.createdAt,
      updated_at: f.updatedAt,
    }));

    return NextResponse.json({
      data: transformedForms,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching forms:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const body = await request.json();

    const form = await prisma.form.create({
      data: {
        code: body.code,
        name: body.name,
        purpose: body.purpose || null,
        language: body.language || 'en',
        version: body.version || 1,
        isActive: body.is_active || false,
        attachmentId: body.attachment_id || null,
        createdBy: session.user?.id || null,
      },
    });

    // Transform to snake_case for frontend
    const transformedForm = {
      id: form.id,
      code: form.code,
      name: form.name,
      purpose: form.purpose,
      language: form.language,
      version: form.version,
      is_active: form.isActive,
      attachment_id: form.attachmentId,
      created_by: form.createdBy,
      created_at: form.createdAt,
      updated_at: form.updatedAt,
    };

    return NextResponse.json(transformedForm, { status: 201 });
  } catch (error) {
    console.error('Error creating form:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
