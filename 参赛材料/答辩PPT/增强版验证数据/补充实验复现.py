"""Reproducible supplemental evidence; no changes to application algorithms."""
from pathlib import Path
import sys, json, time, statistics, platform, os, subprocess
from dataclasses import replace
from copy import deepcopy
SOURCE_DIR=Path(__file__).resolve().parent
ROOT=next(p for p in SOURCE_DIR.parents if (p/'engine.py').is_file())
BUILD=SOURCE_DIR/'复现实验输出'
BUILD.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from engine import Config, create_scene, build_design, evaluate_design, route_catalog, simulate, measure_path
from map_document import MapDocument
from image_map import scene_from_image
from reporting import export_result, write_csv, write_json
OUT=BUILD
OUT.mkdir(parents=True,exist_ok=True)
facts={}
def announce(s): print(s,flush=True)

# Timing includes routing, design-order site selection and three evaluation plans.
# Imports, UI, file export and plotting excluded. One unrecorded warmup.
rows=[]
if '--reuse-timing' in sys.argv:
    import csv
    with (OUT/'runtime_raw.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=[{k:float(v) for k,v in row.items()} for row in csv.DictReader(f)]
else:
    evaluate_design(build_design(Config(order_count=5)))
    for n in (30,60,120):
        for rep in range(1,4):
            c=Config(order_count=n)
            t=time.perf_counter(); d=build_design(c); t1=time.perf_counter()
            r=evaluate_design(d); t2=time.perf_counter()
            row={'orders':n,'repeat':rep,'design_s':t1-t,'evaluation_s':t2-t1,'total_s':t2-t,
                 'candidate_count':len(d['candidates']),'completed':r['plans']['combined']['stats']['delivered_orders']}
            rows.append(row); announce(row)
write_csv(OUT/'runtime_raw.csv',rows)
facts['runtime']=[{'orders':n,**{k:statistics.median(r[k] for r in rows if r['orders']==n) for k in ('design_s','evaluation_s','total_s')},
                   'min_s':min(r['total_s'] for r in rows if r['orders']==n),'max_s':max(r['total_s'] for r in rows if r['orders']==n)} for n in (30,60,120)]
facts['environment']={'python':platform.python_version(),'platform':platform.platform(),'processor':os.environ.get('PROCESSOR_IDENTIFIER',''),
                      'method':'one unrecorded warmup; 3 sequential repeats per load; perf_counter; no UI/import/export/plotting',
                      'load_window_s':1200,'scenario':'normal','note':'30/60/120 orders all in normal scenario; not the previous peak scenario'}

# Same map, same seeds/config; only B1 manual height changed and saved/reopened.
c=Config()
doc=MapDocument(create_scene(c)); doc.save(OUT/'case_before_scene.json')
before=evaluate_design(build_design(c,OUT/'case_before_scene.json'))
doc.update('buildings','B1',{'height':52});doc.save(OUT/'case_after_scene.json')
after=evaluate_design(build_design(c,OUT/'case_after_scene.json'))
assert before['plans']['combined']['orders']==after['plans']['combined']['orders']
assert before['scene']['buildings'][0]['height']==32 and after['scene']['buildings'][0]['height']==52
export_result(before,OUT/'case_before');export_result(after,OUT/'case_after')
changed=[(k,before['routes'][k],v) for k,v in after['routes'].items() if v and before['routes'][k] and v['distance']>before['routes'][k]['distance']+1e-6]
used_keys={j['route_key'] for j in after['plans']['fixed']['jobs']}
key,lo,hi=max((z for z in changed if z[0] in used_keys),key=lambda z:z[2]['distance']-z[1]['distance'])
facts['case']={'building':'B1','height_before':32,'height_after':52,'route_key':key,'route_before_m':lo['distance'],'route_after_m':hi['distance'],
               'changed_route_count':len(changed),'before_pads':before['plans']['combined']['pad_ids'],'after_pads':after['plans']['combined']['pad_ids'],
               'before_stats':before['plans']['combined']['stats'],'after_stats':after['plans']['combined']['stats'],
               'case_type':'API-driven component edit/save/reopen/recompute; simulated map; not GUI recording'}
job=next(j for j in after['plans']['fixed']['jobs'] if j['route_key']==key)
facts['case']['job']=job
facts['case']['job_before']=next(j for j in before['plans']['fixed']['jobs'] if j['order_id']==job['order_id'])
facts['case']['trace_plan']='fixed'
announce(facts['case'])

# Fixed endpoints; planner ablation only, without site re-selection or dispatch.
scene=create_scene(c)
catalogs={v:route_catalog(scene,replace(c,risk_weight=v)) for v in (0,2)}
keys=[k for k in catalogs[0] if catalogs[0][k] and catalogs[2][k]]
ab=[{'route_key':k,'distance_lambda0_m':catalogs[0][k]['distance'],'distance_lambda2_m':catalogs[2][k]['distance'],
     'exposure_lambda0':catalogs[0][k]['exposure'],'exposure_lambda2':catalogs[2][k]['exposure']} for k in keys]
write_csv(OUT/'route_ablation_raw.csv',ab)
facts['ablation']={'route_pairs':len(keys),'unreachable_lambda0':sum(v is None for v in catalogs[0].values()),'unreachable_lambda2':sum(v is None for v in catalogs[2].values()),
                 'mean_distance0':statistics.mean(r['distance_lambda0_m'] for r in ab),'mean_distance2':statistics.mean(r['distance_lambda2_m'] for r in ab),
                 'mean_exposure0':statistics.mean(r['exposure_lambda0'] for r in ab),'mean_exposure2':statistics.mean(r['exposure_lambda2'] for r in ab)}
announce(facts['ablation'])

# Actual failure behavior, preserving error messages and simulator failure records.
exceptions=[]
for name,change in [('尺度未确认',lambda s:s.update(image_import={'scale_confirmed':False})),
                    ('楼高未确认',lambda s:s['buildings'][0].update(height_confirmed=False)),
                    ('坐标越界',lambda s:s['pads'][0].update(x=-1))]:
    s=deepcopy(scene);change(s)
    try: create_scene(c,s)
    except ValueError as e:exceptions.append({'case':name,'result':'blocked','message':str(e)})
    else:raise AssertionError(name)
s=deepcopy(scene); routes={k:None for k in before['routes']}
orders=[{'id':'O001','destination_id':'D1','created_at':0,'due_at':600}]
p=simulate(s,c,['S1','S5'],orders,routes)
assert p['stats']['unreachable_orders']==1
exceptions.append({'case':'所有指定航路不可达','result':p['failed'][0]['failure_type'],'message':p['failed'][0]['reason'],'stats':p['stats']})
s.update(width=100,height=100,buildings=[],risk_zones=[],closure=None,pads=[{'id':'S1','x':0,'y':50},{'id':'S2','x':100,'y':50}])
routes={'S1:D1':measure_path(s,[(0,50),(50,50),(100,50)]),'S2:D2':measure_path(s,[(100,50),(50,50),(0,50)]),'S1:D2':None,'S2:D1':None}
orders=[{'id':'O001','destination_id':'D1','created_at':0,'due_at':600},{'id':'O002','destination_id':'D2','created_at':0,'due_at':600}]
p=simulate(s,Config(drone_count=2,speed=10,separation=10,max_airspace_delay=0),['S1','S2'],orders,routes)
assert p['stats']['airspace_failed_orders']==1 and p['stats']['completion_rate']==.5
exceptions.append({'case':'零额外等待的对向航路','result':p['failed'][0]['failure_type'],'message':p['failed'][0]['reason'],'stats':p['stats']})
draft=scene_from_image(ROOT/'data'/'图片导入示例.png')
assert draft['image_import']['scale_confirmed'] is False
assert all(b.get('height_confirmed') is False for b in draft['buildings'])
facts['image_import']={'candidate_buildings':len(draft['buildings']),'scale_confirmed':False,'all_heights_pending':True}
facts['exceptions']=exceptions
write_json(OUT/'evidence_summary.json',facts)
write_json(BUILD/'evidence.json',facts)

# Actual application SVG map export, filtered to the traced route for readability.
from reporting import map_svg
for label,r in [('before',before),('after',after)]:
    filtered=deepcopy(r);filtered['routes']={key:r['routes'][key]}
    (BUILD/f'case-{label}.svg').write_text(map_svg(filtered,'fixed'),encoding='utf-8')
announce({'done':str(OUT)})
