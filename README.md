# CMI ทั้งประเทศ

Dashboard Mean AdjRW / CMI ผู้ป่วยใน ของโรงพยาบาลสังกัดสำนักงานปลัดกระทรวงสาธารณสุข 902 แห่ง (12 เขตสุขภาพ)
ข้อมูลจาก cmi.moph.go.th ดึงอัตโนมัติด้วย GitHub Actions (`.github/workflows/update-cmi.yml`)

- `data/hospitals.xlsx` → `scripts/build_master.py` → `data/master.json` (ระดับบริการ เตียง ปชก.UC)
- `scripts/fetch_cmi.py` ดึงรายงานราย รพ. และภาพรวมเขต/ประเทศ
- `scripts/build_data.py` สร้าง `data/<ปีงบ>/r1..r12.json`, `r0.json`, `codes.json`, `meta.json`, `years.json`

พัฒนาและออกแบบโดย นายแพทย์กุลพล ตั้งรัตนาพิบูล นายแพทย์ชำนาญการ (ด้านเวชกรรม) ปฏิบัติหน้าที่ผู้อำนวยการโรงพยาบาลสองแคว อำเภอสองแคว จังหวัดน่าน
