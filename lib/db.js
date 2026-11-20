import 'server-only';
import { Pool } from 'pg';
import { readFileSync } from 'node:fs';
import path from 'node:path';

let pool;
export function database() {
  if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is not configured');
  if (!pool) pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 3, connectionTimeoutMillis: 10000, ssl: { ca: readFileSync(path.join(process.cwd(), 'certs', 'supabase-ca.crt')), rejectUnauthorized: true } });
  return pool;
}
