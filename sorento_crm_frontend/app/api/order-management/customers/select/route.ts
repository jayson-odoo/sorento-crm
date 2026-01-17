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

    const customers = await prisma.customer.findMany({
      where: {
        isActive: true,
      },
      orderBy: {
        customerName: 'asc',
      },
      select: {
        id: true,
        customerCode: true,
        customerName: true,
      },
    });

    // Transform to snake_case for frontend
    const transformedCustomers = customers.map((customer: { id: string; customerCode: string; customerName: string }) => ({
      id: customer.id,
      customer_code: customer.customerCode,
      customer_name: customer.customerName,
    }));

    return NextResponse.json(transformedCustomers);
  } catch (error) {
    console.error('Error fetching customers for select:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
