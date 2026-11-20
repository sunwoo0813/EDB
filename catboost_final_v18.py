from pathlib import Path
import argparse, hashlib, json, shutil, time
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

REQUIRED=['area.csv','industry.csv','quarter.csv','sales.csv','rent.csv','store.csv','floating_pop.csv','resident_pop.csv','worker_pop.csv','facility.csv']
SEED=42
ITERATIONS=500
EARLY_STOPPING_ROUNDS=50

def prepare(DATA_DIR):
    DATA_DIR=Path(DATA_DIR)
    missing=[f for f in REQUIRED if not (DATA_DIR/f).is_file()]
    if missing: raise FileNotFoundError(f'필요한 원본 CSV가 없습니다: {missing}')
    def read(name, columns):
        return pd.read_csv(DATA_DIR/name,usecols=columns,dtype={'area_code':str,'industry_code':str,'district_code':str,'area_type_code':str})

    ak=['area_code','quarter_code'];ik=['area_code','industry_code','quarter_code']
    sales_patterns=['weekday_sales_amt','weekend_sales_amt']+[d+'_sales_amt' for d in ['mon','tue','wed','thu','fri','sat','sun']]+['time_'+h+'_sales_amt' for h in ['00_06','06_11','11_14','14_17','17_21','21_24']]+[f'age_{a}_sales_amt' for a in ['10','20','30','40','50','60_plus']]+['male_sales_amt','female_sales_amt']
    pop_patterns=['male_floating_pop','female_floating_pop']+[f'age_{a}_floating_pop' for a in ['10','20','30','40','50','60_plus']]+['time_'+h+'_floating_pop' for h in ['00_06','06_11','11_14','14_17','17_21','21_24']]
    facility_cols=['facility_total_cnt','subway_station_cnt','bus_stop_cnt','university_cnt','supermarket_cnt']
    area=read('area.csv',['area_code','area_name','district_code','area_type_code'])
    industry=read('industry.csv',['industry_code','industry_name'])
    quarter=read('quarter.csv',['quarter_code','quarter_year','quarter_no']).sort_values(['quarter_year','quarter_no'])
    quarter['q_index']=quarter.quarter_year*4+quarter.quarter_no-1
    if quarter.quarter_code.duplicated().any() or not quarter.q_index.diff().dropna().eq(1).all():raise ValueError('분기 코드가 중복되거나 연속되지 않습니다.')
    qmap=dict(zip(quarter.quarter_code,quarter.q_index))
    if len(quarter)!=16 or int(quarter.quarter_code.iloc[-1])!=20262: raise ValueError('2022년 3분기부터 2026년 2분기까지 16분기를 확인하세요.')
    latest=int(quarter.q_index.max())
    sales=read('sales.csv',ik+['month_sales_amt','month_sales_cnt']+sales_patterns)
    store=read('store.csv',ik+['total_store_cnt','general_store_cnt','franchise_store_cnt','open_rate','open_store_cnt','close_rate','close_store_cnt'])
    floating=read('floating_pop.csv',ak+['total_floating_pop']+pop_patterns)
    resident=read('resident_pop.csv',ak+['total_resident_pop','total_household_cnt','apt_household_cnt'])
    worker=read('worker_pop.csv',ak+['total_worker_pop'])
    facility=read('facility.csv',ak+facility_cols)
    rent=read('rent.csv',ak+['converted_rent'])
    for name,df,keys in [('area',area,['area_code']),('industry',industry,['industry_code']),('sales',sales,ik),('rent',rent,ak),('store',store,ik),('floating_pop',floating,ak),('resident_pop',resident,ak),('worker_pop',worker,ak),('facility',facility,ak)]:
        if df[keys].isna().any().any() or df.duplicated(keys).any():raise ValueError(f'{name}: 키 누락 또는 중복')
        if 'quarter_code' in df and not df.quarter_code.isin(qmap).all():raise ValueError(f'{name}: 분기 코드 오류')
    print('원본 CSV와 키 확인 완료')

    def div(num,den):
        return num/den.replace(0,np.nan)
    def add_history(frame,keys,base):
        g=frame.groupby(keys,sort=False,observed=True)
        for col in base:
            prev=g[col].shift(1)
            frame[col+'_rate1']=div(frame[col]-prev,prev)
        return frame

    # 모든 분기별 입력을 각각 상권·분기 또는 상권·업종·분기로 결합합니다.
    industry_panel=sales.merge(store,on=ik,how='outer',indicator=True,validate='one_to_one')
    if not industry_panel.pop('_merge').eq('both').all():raise ValueError('매출과 점포의 상권·업종·분기가 다릅니다.')
    activity=industry_panel.groupby(ak,as_index=False).agg(area_sales=('month_sales_amt','sum'),area_stores=('total_store_cnt','sum'),area_open=('open_store_cnt','sum'),area_close=('close_store_cnt','sum'))
    area_panel=rent.merge(floating,on=ak,how='outer',indicator=True,validate='one_to_one')
    if not area_panel.pop('_merge').eq('both').all():raise ValueError('임대료와 유동인구의 상권·분기가 다릅니다.')
    for other in [resident,worker,facility,activity]:area_panel=area_panel.merge(other,on=ak,how='left',validate='one_to_one')
    area_panel=area_panel.merge(area,on='area_code',how='left',validate='many_to_one')
    area_panel['q_index']=area_panel.quarter_code.map(qmap)
    area_panel=area_panel.sort_values(['area_code','q_index']).reset_index(drop=True)
    area_panel=add_history(area_panel,['area_code'],['converted_rent','area_sales','area_stores','total_floating_pop','total_resident_pop','total_worker_pop'])
    ag=area_panel.groupby('area_code',sort=False)
    for col in ['converted_rent','area_sales','area_stores','total_floating_pop']:
        area_panel[col+'_volatility4']=ag[col+'_rate1'].transform(lambda x:x.rolling(3,min_periods=3).std())
    area_panel['apt_household_share']=div(area_panel.apt_household_cnt,area_panel.total_household_cnt)
    for c in pop_patterns:area_panel[c+'_share']=div(area_panel[c],area_panel.total_floating_pop)

    area_features=['total_floating_pop','total_resident_pop','total_worker_pop','total_household_cnt','apt_household_share','area_sales','area_stores','area_open','area_close']+facility_cols
    area_features += [c+'_rate1' for c in ['converted_rent','area_sales','area_stores','total_floating_pop','total_resident_pop','total_worker_pop']]
    area_features += [c+'_volatility4' for c in ['converted_rent','area_sales','area_stores','total_floating_pop']]
    area_features += [c+'_share' for c in pop_patterns]
    industry_panel=industry_panel.merge(area_panel[ak+['area_name','district_code','area_type_code']+area_features],on=ak,how='left',validate='many_to_one')
    industry_panel=industry_panel.merge(industry,on='industry_code',how='left',validate='many_to_one')
    industry_panel['q_index']=industry_panel.quarter_code.map(qmap)
    industry_panel=industry_panel.sort_values(['area_code','industry_code','q_index']).reset_index(drop=True)
    industry_panel=add_history(industry_panel,['area_code','industry_code'],['month_sales_amt','month_sales_cnt','total_store_cnt'])
    ig=industry_panel.groupby(['area_code','industry_code'],sort=False)
    industry_panel['sales_volatility4']=ig.month_sales_amt_rate1.transform(lambda x:x.rolling(3,min_periods=3).std())
    industry_panel['sales_yoy_rate']=div(industry_panel.month_sales_amt-ig.month_sales_amt.shift(4),ig.month_sales_amt.shift(4))
    industry_panel['sales_per_store']=div(industry_panel.month_sales_amt,industry_panel.total_store_cnt)
    industry_panel['franchise_share']=div(industry_panel.franchise_store_cnt,industry_panel.total_store_cnt)
    industry_panel['net_open_close']=industry_panel.open_store_cnt-industry_panel.close_store_cnt
    for c in sales_patterns:industry_panel[c+'_share']=div(industry_panel[c],industry_panel.month_sales_amt)
    sales_extra=['month_sales_cnt','total_store_cnt','total_floating_pop','sales_per_store','month_sales_amt_rate1','month_sales_cnt_rate1','total_store_cnt_rate1','sales_volatility4','sales_yoy_rate','general_store_cnt','franchise_store_cnt','franchise_share','open_rate','open_store_cnt','close_rate','close_store_cnt','net_open_close']+[c+'_share' for c in sales_patterns]+area_features
    # 중복된 이름은 순서를 유지하며 한 번만 사용합니다.
    sales_extra=list(dict.fromkeys(sales_extra));rent_extra=list(dict.fromkeys(area_features))
    for name,panel in [('area',area_panel),('industry',industry_panel)]:
        if panel[['q_index','area_name','district_code','area_type_code']].isna().any().any():raise ValueError(f'{name}: 상권 또는 분기 정보 누락')
    if industry_panel.industry_name.isna().any():raise ValueError('업종명 누락')
    print('확장 입력 준비:',len(industry_panel),'매출 행 /',len(area_panel),'임대료 행')

    configs={
     'sales':{'panel':industry_panel,'keys':['area_code','industry_code'],'target':'month_sales_amt','extra':sales_extra,'loss':'MAE'},
     'rent':{'panel':area_panel,'keys':['area_code'],'target':'converted_rent','extra':rent_extra,'loss':'MAE'},
     'store':{'panel':industry_panel,'keys':['area_code','industry_code'],'target':'total_store_cnt','extra':['open_store_cnt','close_store_cnt','net_open_close','month_sales_amt'],'loss':'RMSE'},
     'floating_pop':{'panel':area_panel,'keys':['area_code'],'target':'total_floating_pop','extra':['total_resident_pop','total_worker_pop'],'loss':'RMSE'},
    }
    return configs, latest


def make_dataset(cfg):
    keys=cfg['keys'];target=cfg['target'];d=cfg['panel'].sort_values(keys+['q_index']).reset_index(drop=True).copy()
    if not d.groupby(keys,sort=False).q_index.diff().dropna().eq(1).all():raise ValueError(f'{target}: 분기 누락')
    if d[target].isna().any() or d[target].lt(0).any():raise ValueError(f'{target}: 값 누락 또는 음수')
    g=d.groupby(keys,sort=False)[target]
    d['target_current']=d[target];d['target_previous']=g.shift(1);d['target_year_ago']=g.shift(3)
    d['target_mean4']=g.rolling(4,min_periods=4).mean().reset_index(level=list(range(len(keys))),drop=True).sort_index()
    d['target_change']=d.target_current-d.target_previous;d['y_next']=g.shift(-1)
    d['forecast_index']=d.q_index+1;d['forecast_quarter']=(d.forecast_index%4+1).astype(str)
    cats=keys+['district_code','area_type_code','forecast_quarter']
    features=list(dict.fromkeys(cats+['target_current','target_previous','target_year_ago','target_mean4','target_change']+cfg['extra']))
    for c in cats:
        if d[c].isna().any():raise ValueError(f'범주형 입력 누락: {c}')
        d[c]=d[c].astype(str)
    for c in features:
        if c not in cats:d[c]=pd.to_numeric(d[c],errors='raise').replace([np.inf,-np.inf],np.nan)
    return d[d.target_mean4.notna()].copy(),features,cats



def labels(d,name):
    y=d.y_next.to_numpy(float); current=d.target_current.to_numpy(float)
    return np.log1p(y)-np.log1p(current) if name=='sales' else y-current

def restore(raw,d,name):
    current=d.target_current.to_numpy(float)
    if name=='sales': values=np.expm1(np.clip(raw+np.log1p(current),-20,40))
    elif name=='rent': values=current+.25*raw
    else: values=current+raw
    return np.maximum(values,0)

def make_model(trees,loss):
    return CatBoostRegressor(iterations=trees,depth=6,learning_rate=.05,loss_function=loss,random_seed=SEED,verbose=False,allow_writing_files=False,thread_count=-1)

def code_for_index(idx): return (idx//4)*10+idx%4+1

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def run(data_dir,output_dir,mode='train'):
    data_dir=Path(data_dir); output_dir=Path(output_dir)
    if mode=='predict' and not output_dir.is_dir(): raise FileNotFoundError(f'저장 모델 폴더가 없습니다: {output_dir}')
    output_dir.mkdir(parents=True,exist_ok=True)
    configs,latest=prepare(data_dir)
    if mode=='train':
        inputs={name:{'sha256':digest(data_dir/name)} for name in REQUIRED}
        (output_dir/'input_files.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,cfg in configs.items():
        start=time.time(); print('\n===== '+name+' =====',flush=True)
        d,features,cats=make_dataset(cfg)
        full=d[(d.forecast_index<=latest)&d.y_next.notna()]
        early=d[(d.forecast_index==latest)&d.y_next.notna()]
        inner=d[(d.forecast_index<latest)&d.y_next.notna()]
        future=d[d.q_index==latest].copy()
        expected=cfg['panel'].loc[cfg['panel'].q_index==latest,cfg['keys']].drop_duplicates().shape[0]
        if min(len(inner),len(early),len(full),len(future))==0 or len(future)!=expected: raise ValueError(f'{name}: 학습/예측 행 수 오류: {len(future)} / {expected}')
        if future.duplicated(cfg['keys']).any(): raise ValueError(f'{name}: 예측 키가 중복되었습니다.')
        if not full.forecast_index.le(latest).all() or not future.forecast_index.eq(latest+1).all(): raise ValueError('분기 경계 오류')
        model_path=output_dir/(name+'_model.cbm'); meta_path=output_dir/(name+'_features.json')
        if mode=='train':
            selector=make_model(ITERATIONS,cfg['loss'])
            selector.fit(inner[features],labels(inner,name),cat_features=cats,eval_set=(early[features],labels(early,name)),early_stopping_rounds=EARLY_STOPPING_ROUNDS,verbose=False)
            best=selector.best_iteration_; trees=max(1,int(best+1)) if best is not None and best>=0 else ITERATIONS
            model=make_model(trees,cfg['loss']); model.fit(full[features],labels(full,name),cat_features=cats,verbose=False)
            before=model.predict(future[features]); model.save_model(str(model_path))
            loaded=CatBoostRegressor(); loaded.load_model(str(model_path)); after=loaded.predict(future[features])
            if not np.allclose(before,after,rtol=1e-12,atol=1e-12): raise ValueError(f'{name}: 저장 전후 예측 불일치')
            metadata={'model':name,'target':cfg['target'],'features':features,'categorical_features':cats,'training_end_quarter':code_for_index(latest),'early_stopping_target_quarter':code_for_index(latest),'forecast_quarter':code_for_index(latest+1),'trees':trees,'max_iterations':ITERATIONS,'loss':cfg['loss'],'depth':6,'learning_rate':.05,'seed':SEED,'target_transform':'log1p(next)-log1p(current)' if name=='sales' else 'next-current','output_rule':'expm1(clip(raw+log1p(current),-20,40))' if name=='sales' else ('current+0.25*raw' if name=='rent' else 'current+raw'),'negative_clipped_to_zero':True,'training_rows':len(full),'prediction_rows':len(future)}
            meta_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            raw=after
        else:
            metadata=json.loads(meta_path.read_text(encoding='utf-8'))
            if metadata['features']!=features or metadata['categorical_features']!=cats or metadata['training_end_quarter']!=code_for_index(latest): raise ValueError(f'{name}: 모델의 입력 또는 기준 분기가 현재 데이터와 다릅니다.')
            model=CatBoostRegressor(); model.load_model(str(model_path)); raw=model.predict(future[features]); trees=metadata['trees']
        prediction=restore(raw,future,name)
        if not np.isfinite(prediction).all() or (prediction<0).any(): raise ValueError(f'{name}: 예측값 오류')
        cols=cfg['keys']+['area_name']+(['industry_name'] if 'industry_code' in cfg['keys'] else [])+['quarter_code','target_current']
        result=future[cols].rename(columns={'quarter_code':'input_quarter_code','target_current':'previous_value'}).copy()
        result['forecast_quarter_code']=code_for_index(latest+1); result['prediction']=prediction
        result.to_csv(output_dir/(name+'_forecast.csv'),index=False,encoding='utf-8-sig')
        print(f'학습 행 {len(full):,} | 예측 행 {len(result):,} | 입력 {len(features)}개 | 트리 {trees}개 | {time.time()-start:.1f}초',flush=True)
    print('모델과 예측 결과:',output_dir,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='CatBoost 4개 모델 학습 또는 저장된 모델로 예측')
    parser.add_argument('--data-dir',required=True); parser.add_argument('--output-dir',required=True)
    parser.add_argument('--mode',choices=['train','predict'],default='predict')
    args=parser.parse_args(); run(args.data_dir,args.output_dir,args.mode)
