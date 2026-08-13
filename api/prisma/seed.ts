import { PrismaClient } from '@prisma/client'
import bcrypt from 'bcryptjs'

const prisma = new PrismaClient()

async function main() {
  console.log('Running seed...')

  // Plans
  const plans = [
    { id: 'b0000000-0000-4000-8000-000000000000', name: 'Basic', price_cents: 1000 },
    { id: 'a0000000-0000-4000-8000-000000000000', name: 'Pro', price_cents: 3000 },
    { id: 'e0000000-0000-4000-8000-000000000000', name: 'Premium', price_cents: 5000 },
  ]

  for (const p of plans) {
    await prisma.plan.upsert({
      where: { name: p.name },
      update: { price_cents: p.price_cents },
      create: { id: p.id, name: p.name, price_cents: p.price_cents },
    })
  }

  // Admin user
  const adminId = 'd0000000-0000-4000-8000-000000000000'
  const adminEmail = 'admin@prora.com'
  const adminPassword = 'adminpassword123'
  const password_hash = bcrypt.hashSync(adminPassword, 10)

  await prisma.user.upsert({
    where: { email: adminEmail },
    update: { password_hash },
    create: { id: adminId, email: adminEmail, password_hash, role: 'ADMIN' },
  })

  // Demo customers & subscriptions
  const customers = [
    {
      userId: 'd0000000-0000-4000-8000-000000000001',
      email: 'customer_a@prora.com',
      custId: 'c0000000-0000-4000-8000-000000000000',
      name: 'Demo Customer A (Startup Corp)',
      subId: 'f0000000-0000-4000-8000-000000000000',
      planId: 'b0000000-0000-4000-8000-000000000000',
    },
    {
      userId: 'd0000000-0000-4000-8000-000000000002',
      email: 'customer_b@prora.com',
      custId: 'c0000000-0000-4000-8000-000000000001',
      name: 'Demo Customer B (SaaS Enterprises)',
      subId: 'f0000000-0000-4000-8000-000000000001',
      planId: 'a0000000-0000-4000-8000-000000000000',
    },
    {
      userId: 'd0000000-0000-4000-8000-000000000003',
      email: 'customer_c@prora.com',
      custId: 'c0000000-0000-4000-8000-000000000002',
      name: 'Demo Customer C (Global Logistics)',
      subId: 'f0000000-0000-4000-8000-000000000002',
      planId: 'e0000000-0000-4000-8000-000000000000',
    },
  ]

  const now = new Date()

  for (const s of customers) {
    await prisma.user.upsert({
      where: { email: s.email },
      update: {},
      create: { id: s.userId, email: s.email, password_hash: bcrypt.hashSync('password123', 10), role: 'CUSTOMER' },
    })

    await prisma.customer.upsert({
      where: { id: s.custId },
      update: {},
      create: { id: s.custId, name: s.name, userId: s.userId },
    })

    await prisma.subscription.upsert({
      where: { id: s.subId },
      update: {},
      create: {
        id: s.subId,
        customerId: s.custId,
        planId: s.planId,
        status: 'ACTIVE',
        cycle_start: now,
        cycle_end: new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000),
        version: 1,
      },
    })
  }

  console.log('Seed complete')
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(async () => {
    await prisma.$disconnect()
  })
