#!/usr/bin/env python3
"""data/hospitals.xlsx (รายชื่อ รพ. สป.สธ. 902 แห่ง) -> data/master.json

คอลัมน์ที่ใช้: เขต, จังหวัด, รหัส, หน่วยบริการ, ประเภท, ระดับขีดความสามารถ,
จำนวนเตียงตามจริง (กบรส ณ 15/3/2567), ปชช UC 1เม.ย.66, กลุ่มระดับบริการ
ใช้: python scripts/build_master.py
"""
import json, os
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ws = openpyxl.load_workbook(os.path.join(ROOT, 'data', 'hospitals.xlsx'), read_only=True, data_only=True).worksheets[0]
rows = list(ws.iter_rows(values_only=True))
hdr = [str(h or '').strip() for h in rows[0]]
col = lambda key: next(i for i, h in enumerate(hdr) if h.startswith(key))
c = dict(reg=col('เขต'), chw=col('จังหวัด'), code=col('รหัส'), name=col('หน่วยบริการ'), type=col('ประเภท'),
         lvl=col('ระดับขีดความสามารถ'), beds=col('จำนวนเตียง'), pop=col('ปชช UC'), sg=col('กลุ่มระดับบริการ'))
H = []
for r in rows[1:]:
    if r[c['code']] is None:
        continue
    H.append([int(r[c['reg']]), str(r[c['code']]).strip().zfill(5), str(r[c['name']]).strip(), str(r[c['chw']]).strip(),
              str(r[c['type']]).strip(), str(r[c['lvl']]).strip(), int(r[c['beds']] or 0), int(r[c['pop']] or 0),
              str(r[c['sg']]).strip()])
out = {'source': 'ระดับบริการ เตียงจริง (กบรส. ณ 15/3/2567) และ ปชก.UC (1 เม.ย. 66) จากไฟล์ hospitals.xlsx',
       'cols': ['region', 'hcode', 'name', 'chw', 'type', 'lvl', 'beds', 'pop', 'sgroup'], 'H': H}
with open(os.path.join(ROOT, 'data', 'master.json'), 'w', encoding='utf-8') as f:
    f.write('{"source":%s,"cols":%s,"H":[\n%s\n]}\n' % (json.dumps(out['source'], ensure_ascii=False), json.dumps(out['cols']),
            ',\n'.join(json.dumps(h, ensure_ascii=False) for h in H)))
print('master.json:', len(H), 'รพ.', {r: sum(1 for h in H if h[0] == r) for r in range(1, 13)})
