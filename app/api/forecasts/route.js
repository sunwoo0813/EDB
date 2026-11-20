import { database } from '../../../lib/db';

export const dynamic = 'force-dynamic';
export async function POST(request) {
  try {
    const body = await request.json();
    const { industry, districts, types, maxRent } = body;
    if (!/^CS\d{6}$/.test(industry || '') || !Array.isArray(districts) || districts.length < 1 || districts.length > 25 || districts.some(x => !/^\d{5}$/.test(x)) || !Array.isArray(types) || types.length < 1 || types.length > 4 || types.some(x => !/^[ADRU]$/.test(x)) || (maxRent !== null && (!Number.isFinite(maxRent) || maxRent < 0 || maxRent > 100000000))) {
      return Response.json({ error: '조회 조건을 확인해 주세요.' }, { status: 400 });
    }
    const query = `SELECT trim(a.area_code) AS area_code, a.area_name, trim(a.district_code) AS district_code,
      d.district_name, trim(a.area_type_code) AS area_type_code, t.area_type_name,
      p.pred_sales_amt, p.pred_store_cnt, ap.pred_floating_pop, ap.pred_rent,
      s.month_sales_amt AS previous_sales_amt, st.total_store_cnt AS previous_store_cnt,
      f.total_floating_pop AS previous_floating_pop, r.converted_rent AS previous_rent
      FROM public.industry_pred p
      JOIN public.area a ON a.area_code = p.area_code
      JOIN public.district d ON d.district_code = a.district_code
      JOIN public.area_type t ON t.area_type_code = a.area_type_code
      JOIN public.area_pred ap ON ap.area_code = p.area_code AND ap.target_quarter_code = p.target_quarter_code
      LEFT JOIN public.sales s ON s.area_code = p.area_code AND s.industry_code = p.industry_code AND s.quarter_code = '20262'
      LEFT JOIN public.store st ON st.area_code = p.area_code AND st.industry_code = p.industry_code AND st.quarter_code = '20262'
      LEFT JOIN public.floating_pop f ON f.area_code = p.area_code AND f.quarter_code = '20262'
      LEFT JOIN public.rent r ON r.area_code = p.area_code AND r.quarter_code = '20262'
      WHERE p.target_quarter_code = '20263' AND p.industry_code = $1
      AND a.district_code::text = ANY($2::text[]) AND a.area_type_code::text = ANY($3::text[])
      AND ($4::numeric IS NULL OR ap.pred_rent <= $4::numeric)
      ORDER BY a.area_code`;
    const result = await database().query(query, [industry, districts, types, maxRent]);
    return Response.json({ rows: result.rows });
  } catch (error) {
    console.error('Forecast query failed:', error.message);
    return Response.json({ error: '예측 데이터를 불러오지 못했습니다. 서버 설정을 확인해 주세요.' }, { status: 503 });
  }
}
