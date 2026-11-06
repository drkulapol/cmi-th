#!/usr/bin/env python3
"""ข้อมูลดิบจาก fetch_cmi.py -> ไฟล์ของ dashboard cmi-th

  data/<ปีงบ>/codes.json   รายชื่อรหัส PDx / DRG ที่ใช้ร่วมกันทุกเขต (ลำดับคงที่ ต่อท้ายรหัสใหม่)
  data/<ปีงบ>/r<เขต>.json  ข้อมูลรายเขต รูปแบบเดียวกับ data-<ปีงบ>.json ของ cmi-rh1 (ไม่มี PDXC/DRGC)
  data/<ปีงบ>/r0.json      รายงานภาพรวมระดับประเทศ (R1P/R1S/R1T/R1B) สำหรับมุมมองทั้งประเทศ
  meta.json, years.json

ใช้: python scripts/build_data.py --raw /tmp/cmi --fy 2569
"""
import argparse, glob, json, os, re
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TH = timezone(timedelta(hours=7))
TM = {'ต.ค.': 0, 'พ.ย.': 1, 'ธ.ค.': 2, 'ม.ค.': 3, 'ก.พ.': 4, 'มี.ค.': 5,
      'เม.ย.': 6, 'พ.ค.': 7, 'มิ.ย.': 8, 'ก.ค.': 9, 'ส.ค.': 10, 'ก.ย.': 11}


def num(s):
    s = (s or '').replace(',', '').strip()
    if s in ('', '-'):
        return None
    try:
        f = float(s)
    except ValueError:
        return s
    return int(f) if f.is_integer() else f


def cnt(s):  # "49(22.37)" -> (49, 22.37)
    m = re.match(r'([\d,\.]+)\(([\d\.]+)\)', s.replace(' ', ''))
    return (num(m.group(1)), num(m.group(2))) if m else (num(s), None)


def first_table(x):
    return x[0] if x else None


def dump(obj, path):
    """เขียน JSON แถวละบรรทัด เพื่อให้ git เก็บเฉพาะส่วนที่เปลี่ยน"""
    parts = []
    for k, v in obj.items():
        if isinstance(v, list) and v:
            body = ',\n'.join(json.dumps(x, ensure_ascii=False, separators=(',', ':')) for x in v)
            parts.append(f'{json.dumps(k)}:[\n{body}\n]')
        else:
            parts.append(f'{json.dumps(k)}:{json.dumps(v, ensure_ascii=False, separators=(",", ":"))}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{' + ',\n'.join(parts) + '}\n')


def macro_rows(raw, key, split_code, lab):
    rows = []
    for mm, per in (('mm1', 'ครั้งที่ 1'), ('mm2', 'ครั้งที่ 2')):
        t = first_table(raw['macro'].get(f'{key}_{mm}'))
        for r in (t['rows'] if t else []):
            if not r or not r[0]:
                continue
            lead = [x.strip() for x in r[0].split(':', 1)] if split_code else [r[0]]
            if split_code and len(lead) == 1:
                lead = ['', lead[0]]
            rows.append([lab[per]] + lead + [num(x) for x in r[1:]])
    return rows


def region_summary(raw, fy, total_name):
    yy1, yy2 = str(fy - 1)[-2:], str(fy)[-2:]
    lab = {'ครั้งที่ 1': f'ครั้งที่ 1 (ต.ค.{yy1}-มี.ค.{yy2})', 'ครั้งที่ 2': f'ครั้งที่ 2 (ต.ค.{yy1}-ก.ย.{yy2})'}
    R1B = []
    t = first_table((raw.get('region_rpt') or {}).get('ipd_percentage'))
    for r in (t['rows'] if t else []):
        if len(r) < 12:
            continue
        a, b = ([x.strip() for x in r[0].split(':', 1)] + [''])[:2] if r[0] else ['รวม', total_name]
        v = [num(r[1]), num(r[2]), num(r[3])] + [x for c in r[4:12] for x in cnt(c)]
        R1B.append([a, b] + v + [round(v[2] / v[1], 4) if v[1] else None])
    return dict(R1P=macro_rows(raw, 'type3', True, lab), R1S=macro_rows(raw, 'type1', False, lab),
                R1T=macro_rows(raw, 'type2', False, lab), R1B=R1B)


def build_region(raw, master, codes, fy, run, src):
    pdxc, drgc, pdxi, drgi = codes
    spcl = raw['spcl']
    H, BAND, LOW, MON, PDX, DRG, failed = [], [], [], [], [], [], []
    for h in master:
        hc = h[1]
        s = spcl.get(hc) or {}
        ip = first_table(s.get('ipd_percentage'))
        tot = next((r for r in (ip['rows'] if ip else []) if r and r[0] == ''), None)
        base = h[1:9]  # hcode,name,chw,type,lvl,beds,pop,sgroup
        if tot:
            H.append(base + [num(tot[1]), num(tot[2]), num(tot[3])])
            BAND.append([cnt(x)[0] for x in tot[4:12]])
            LOW.append(list(cnt(tot[4])))
            mon = [[0, 0] for _ in range(12)]
            for r in ip['rows']:
                if r and r[0] and r[0].split()[0] in TM:
                    mon[TM[r[0].split()[0]]] = [num(r[2]) or 0, num(r[3]) or 0]
            MON.append(mon)
        else:
            failed.append(f"{h[2]} ({hc})")
            H.append(base + [0, 0, 0]); BAND.append(None); LOW.append(None)
            MON.append([[0, 0] for _ in range(12)])
    for key, out, cl, idx in (('top10pdx', PDX, pdxc, pdxi), ('drg', DRG, drgc, drgi)):
        for i, h in enumerate(master):
            t = first_table((spcl.get(h[1]) or {}).get(key))
            for r in (t['rows'] if t else []):
                if not r or not r[0] or len(r) < 8:
                    continue
                if r[0] not in idx:
                    idx[r[0]] = len(cl); cl.append([r[0], r[1]])
                out.append([i, idx[r[0]], num(r[2]), num(r[3]), num(r[5]), num(r[6]), num(r[7])])
    reg = raw['region']
    D = {'meta': {'fy': fy, 'region': reg, 'run': run, 'failed': failed, 'master': src}}
    D.update(H=H, BAND=BAND, LOW=LOW, MON=MON, PDX=PDX, DRG=DRG)
    D.update(region_summary(raw, fy, f'เขตสุขภาพที่ {reg}'))
    return D


def has_data(d):
    return sum(1 for h in d.get('H', []) if h and (h[8] or 0) > 0)


def load(p):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='/tmp/cmi')
    ap.add_argument('--fy', type=int, required=True)
    a = ap.parse_args()
    fy = a.fy
    M = load(os.path.join(ROOT, 'data', 'master.json'))
    out = os.path.join(ROOT, 'data', str(fy)); os.makedirs(out, exist_ok=True)

    cj = load(os.path.join(out, 'codes.json')) or {'PDXC': [], 'DRGC': []}
    pdxc, drgc = [list(x) for x in cj['PDXC']], [list(x) for x in cj['DRGC']]
    codes = (pdxc, drgc, {c[0]: i for i, c in enumerate(pdxc)}, {c[0]: i for i, c in enumerate(drgc)})

    mp = os.path.join(ROOT, 'meta.json')
    allm = load(mp) or {}
    ym = allm.setdefault('years', {}).setdefault(str(fy), {'regions': {}})
    ym.setdefault('regions', {})
    changed = []
    for f in sorted(glob.glob(os.path.join(a.raw, f'raw_{fy}_r*.json')), key=lambda p: int(re.search(r'_r(\d+)', p).group(1))):
        raw = load(f)
        reg = int(raw['region']); run = raw.get('fetched_at') or datetime.now(TH).isoformat(timespec='seconds')
        path = os.path.join(out, f'r{reg}.json')
        old = load(path)
        if reg == 0:
            new = {'meta': {'fy': fy, 'region': 0, 'run': run}, **region_summary(raw, fy, 'ทั้งประเทศ')}
            if not new['R1S'] and old:
                print('ภาพรวมประเทศ: ไม่ได้ข้อมูล — คงไฟล์เดิม'); continue
        else:
            master = [h for h in M['H'] if h[0] == reg]
            new = build_region(raw, master, codes, fy, run, M['source'])
            ok, oldok = has_data(new), has_data(old or {})
            ym['regions'][str(reg)] = {'run': run, 'hospitals_ok': ok, 'hospitals_total': len(master),
                                       'failed': len(new['meta']['failed'])}
            # กันข้อมูลถอยหลัง (เว็บล่มบางส่วน): ได้ รพ. น้อยกว่าเดิมเกิน 3 แห่ง ไม่เขียนทับ
            if old and ok < oldok - 3:
                print(f'เขต {reg}: ได้ {ok} รพ. น้อยกว่าเดิม {oldok} — คงไฟล์เดิม')
                ym['regions'][str(reg)].update(run=old['meta']['run'], hospitals_ok=oldok); continue
        strip = lambda d: {**d, 'meta': {**d['meta'], 'run': None}}
        if old and strip(old) == strip(new):
            print(f'เขต {reg}: ตัวเลขไม่เปลี่ยน'); continue
        dump(new, path); changed.append(reg)
        print(f'เขต {reg}: เขียน {os.path.relpath(path, ROOT)}' + (f" · มีข้อมูล {has_data(new)}/{len(new['H'])} รพ." if reg else ''))

    dump({'PDXC': pdxc, 'DRGC': drgc}, os.path.join(out, 'codes.json'))
    regs = ym['regions']
    ym['run'] = max([v['run'] for v in regs.values()] or [datetime.now(TH).isoformat(timespec='seconds')])
    ym['hospitals_ok'] = sum(v['hospitals_ok'] for v in regs.values())
    ym['hospitals_total'] = len(M['H'])
    allm['checked'] = datetime.now(TH).isoformat(timespec='seconds')
    with open(mp, 'w', encoding='utf-8') as f:
        json.dump(allm, f, ensure_ascii=False, indent=1)
    ys = sorted({int(y) for y in allm['years']}, reverse=True)
    with open(os.path.join(ROOT, 'years.json'), 'w') as f:
        json.dump({'years': ys, 'default': ys[0]}, f)
    print(f'ปีงบ {fy}: เปลี่ยน {changed or "ไม่มี"} · มีข้อมูลรวม {ym["hospitals_ok"]}/{len(M["H"])} รพ.')


if __name__ == '__main__':
    main()
