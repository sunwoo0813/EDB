import { database } from '../../../lib/db';

export const dynamic = 'force-dynamic';
export async function GET() {
  try {
    const db = database();
    const [industries, districts, types] = await Promise.all([
      db.query('SELECT industry_code AS code, industry_name AS name FROM public.industry ORDER BY industry_name'),
      db.query('SELECT district_code AS code, district_name AS name FROM public.district ORDER BY district_name'),
      db.query('SELECT area_type_code AS code, area_type_name AS name FROM public.area_type ORDER BY area_type_code'),
    ]);
    return Response.json({ industries: industries.rows, districts: districts.rows, types: types.rows });
  } catch (error) {
    console.error('Metadata query failed:', error.message);
    return Response.json({ error: '데이터베이스에 연결하지 못했습니다. 서버 설정을 확인해 주세요.' }, { status: 503 });
  }
}
