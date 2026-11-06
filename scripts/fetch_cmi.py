#!/usr/bin/env python3
"""ดึงข้อมูล CMI ทุกโรงพยาบาล (สป.สธ. 902 แห่ง ตาม data/master.json) จาก cmi.moph.go.th

ผลลัพธ์ (ในโฟลเดอร์ --out):
  raw_<ปีงบ>_r<เขต>.json   ข้อมูลดิบรายเขต (รายงานภาพรวมเขต + รายงานราย รพ.)
  raw_<ปีงบ>_r0.json       รายงานภาพรวมระดับประเทศ

ใช้:  python scripts/fetch_cmi.py                     (ปีงบปัจจุบัน ทุกเขต)
      python scripts/fetch_cmi.py --fy 2569 --regions 2,3
      python scripts/fetch_cmi.py --probe              (ทดสอบว่าเข้าเว็บได้ไหม)
"""
import argparse, json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

BASE = "https://cmi.moph.go.th"
TH = timezone(timedelta(hours=7))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPCL_EPS = ["top10pdx", "drg", "ipd_percentage"]  # menu_id 15, 18, 16
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


class Client:
    def __init__(self, pause=0.15):
        self.local = threading.local()
        self.pause = pause

    def _sess(self):
        if not hasattr(self.local, "s"):
            s = requests.Session(); s.headers["User-Agent"] = UA
            self.local.s, self.local.csrf = s, {}
        return self.local.s

    def token(self, section, fresh=False):
        s = self._sess()
        if fresh or section not in self.local.csrf:
            menu = "15" if section == "spcl" else "1"
            r = s.get(f"{BASE}/report/{section}/index", params={"menu_id": menu}, timeout=60)
            r.raise_for_status()
            tag = BeautifulSoup(r.text, "lxml").select_one("input[name=_csrf]")
            if not tag:
                raise RuntimeError("ไม่พบ _csrf ในหน้าเว็บ (โครงสร้างเว็บอาจเปลี่ยน)")
            self.local.csrf[section] = tag["value"]
        return self.local.csrf[section]

    def post(self, section, ep, params, tries=3):
        last = None
        for a in range(tries):
            try:
                tok = self.token(section, fresh=a > 0)
                r = self._sess().post(f"{BASE}/report/{section}/{ep}", data={**params, "_csrf": tok},
                                      headers={"X-CSRF-Token": tok, "X-Requested-With": "XMLHttpRequest"},
                                      timeout=180)
                time.sleep(self.pause)  # เว้นจังหวะ ไม่ให้เว็บ CMI รับภาระหนัก
                if r.status_code == 200:
                    return r.text
                last = f"HTTP {r.status_code}"
                if r.status_code == 500:  # บาง รพ. ตอบ 500 ถาวร
                    break
            except Exception as e:
                last = str(e)
            time.sleep(3 * (a + 1))
        print(f"  ! {section}/{ep} {params.get('hcode') or 'region ' + str(params.get('region'))}: {last}", file=sys.stderr)
        return None


def parse_tables(html):
    if html is None:
        return None
    soup = BeautifulSoup(html, "lxml")
    out = []
    for t in soup.find_all("table"):
        hdr = [[[c.get_text(strip=True), int(c.get("colspan", 1))] for c in tr.find_all(["th", "td"])]
               for tr in t.select("thead tr")]
        rows = [[c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
                for tr in t.select("tbody tr, tfoot tr")]
        out.append({"hdr": hdr, "rows": rows})
    return out


def current_fy_be(now):
    return now.year + 543 + (1 if now.month >= 10 else 0)


def region_reports(cl, year, region):
    """region = '1'..'12' หรือ '' (ทั้งประเทศ)"""
    macro, reg = {}, {}
    for t in "123":
        for m in "12":
            macro[f"type{t}_mm{m}"] = parse_tables(cl.post("macro", "summaryall", {
                "year": year, "region": region, "chwcode": "", "rdotype": t, "rdomm": m}))
    for ep in SPCL_EPS if region else ["ipd_percentage"]:
        reg[ep] = parse_tables(cl.post("spcl", ep, {
            "year": year, "region": region, "chwcode": "", "hcode": "", "hosptype": "", "servplan": "", "rdorpt": "1"}))
    return macro, reg


def fetch_region(cl, fy_be, region, codes, workers):
    year = str(fy_be - 543)  # เว็บใช้ปีงบ ค.ศ. เช่น 2026 = 2569
    C = {"year": year, "region": region, "codes": codes, "spcl": {}, "err": []}
    C["macro"], C["region_rpt"] = region_reports(cl, year, str(region))

    def one(hc):
        o = {}
        for ep in SPCL_EPS:
            o[ep] = parse_tables(cl.post("spcl", ep, {
                "year": year, "region": "", "chwcode": "", "hcode": hc, "hosptype": "", "servplan": "", "rdorpt": "1"}))
            if o[ep] is None:
                C["err"].append(f"{hc}:{ep}")
            if ep == "top10pdx" and o[ep] and not any(r and r[0] for tb in o[ep] for r in tb["rows"]):
                # ยังไม่มีข้อมูลปีนี้ ไม่ต้องดึง DRG / ipd_percentage ต่อ
                o["drg"] = o["ipd_percentage"] = []
                break
        return hc, o

    with ThreadPoolExecutor(workers) as ex:
        for hc, o in ex.map(one, codes):
            C["spcl"][hc] = o
    return C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fy", type=int, help="ปีงบประมาณ พ.ศ. (ค่าเริ่มต้น = ปีงบปัจจุบัน)")
    ap.add_argument("--regions", default="0-12", help="เช่น 1-12 หรือ 2,5,9 (0 = ภาพรวมประเทศ)")
    ap.add_argument("--out", default="/tmp/cmi")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    now = datetime.now(TH)
    cl = Client()

    if a.probe:
        h = cl.post("spcl", "hosplist", {"region": "1", "chwcode": "55"})
        n = (h or "").count("<option value='")
        print(f"PROBE: hosplist(น่าน)={n} รพ.")
        sys.exit(0 if n > 0 else 1)

    regs = set()
    for part in a.regions.split(","):
        lo, _, hi = part.partition("-")
        regs.update(range(int(lo), int(hi or lo) + 1))
    master = json.load(open(os.path.join(ROOT, "data", "master.json"), encoding="utf-8"))["H"]
    fy = a.fy or current_fy_be(now)
    os.makedirs(a.out, exist_ok=True)
    for r in sorted(regs):
        t0 = time.time()
        if r == 0:
            year = str(fy - 543)
            macro, reg = region_reports(cl, year, "")
            C = {"year": year, "region": 0, "macro": macro, "region_rpt": reg, "err": []}
        else:
            codes = [h[1] for h in master if h[0] == r]
            C = fetch_region(cl, fy, r, codes, a.workers)
        C["fetched_at"] = datetime.now(TH).isoformat(timespec="seconds")
        ok = sum(1 for v in C.get("spcl", {}).values() if v.get("ipd_percentage"))
        with open(os.path.join(a.out, f"raw_{fy}_r{r}.json"), "w", encoding="utf-8") as f:
            json.dump(C, f, ensure_ascii=False, separators=(",", ":"))
        print(f"ปีงบ {fy} เขต {r or 'ประเทศ'}: มีข้อมูล {ok}/{len(C.get('codes', []))} รพ. "
              f"{time.time() - t0:.0f} วินาที; error {len(C['err'])}", flush=True)


if __name__ == "__main__":
    main()
