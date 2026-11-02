# ANC refactor-v1 — วิธีตรวจและทดลอง

Branch นี้เพิ่มการกำหนดเงื่อนไขรถ 20 สเปกจากโจทย์ และคัดกรองรุ่นย่อยเบื้องต้น

## สิ่งที่เปลี่ยน
- แยก `anc_requirements.py` เพื่อกำหนด Brand, Model, Year, ประเภทซ่อม และทุนเป้าหมายสำหรับ 20 สเปก
- `anc_collector.py` ใช้ซ่อมอู่เฉพาะ 10 สเปกแรก และซ่อมห้างเฉพาะ 10 สเปกหลัง ไม่วนทั้งสองประเภท
- คัดกรอง Car ID จากชื่อเครื่องยนต์อย่างระมัดระวัง: >2.0 ลิตร EXCLUDE, 2.0 ลิตรที่ยังไม่มีข้อมูลยืนยัน REVIEW, ต่ำกว่า 2.0 ลิตร COLLECT (candidate)
- แยก YARIS ATIV ออกจาก YARIS ตามชื่อรุ่นในโจทย์
- `--catalog` สร้าง `anc_target_requirements.csv` และ `anc_variant_screening.csv` เพิ่มเพื่อให้ตรวจการคัดกรอง
- ยังใช้ record_key, branch_key, MySQL v4 และระบบ resume เดิม

## รันใน PowerShell (ที่โฟลเดอร์ repository)
```powershell
git status
git switch refactor-v1
git pull --ff-only origin refactor-v1
.\.venv\Scripts\python.exe -m unittest -v test_anc_requirements
.\.venv\Scripts\python.exe anc_collector.py --dry-run
.\.venv\Scripts\python.exe anc_collector.py --catalog --delay 2
```

## คำเตือนก่อนรัน collector จริง
- เครื่องมือข้างต้นยังไม่ได้รัน End-to-End กับเว็บไซต์จริง/MySQL จริงของผู้ใช้
- `--catalog` สร้าง CSV ตรวจรุ่นย่อยแต่ไม่เก็บเบี้ยหรือเขียน MySQL
- รายการ `COLLECT` หมายถึง candidate ไม่ได้ยืนยันว่ารุ่นย่อยนั้นขายในปีรถที่ต้องการหรือมีข้อเสนอ
- ชื่อรุ่นย่อย `2.0cc` เป็นชื่อคลาสเครื่องยนต์ ไม่ใช่ CC จริง
- ค่า CC ที่บันทึกเป็นข้อมูลเบื้องต้นของตระกูลเครื่องยนต์ ยังต้องตรวจปี/รุ่นย่อยจริงอีกครั้ง
- รหัส `car_id` ของหน้าเว็บไม่ใช่หลักฐานรหัสรับประกัน 110
- **ยังไม่รัน `anc_collector.py --limit 1` กับฐานข้อมูลเดิม** เพราะจะเขียนข้อมูลลง MySQL โดยใช้ตาราง v4; หากต้องทดสอบจริง ให้ใช้ `DB_NAME` เป็นฐานข้อมูลใหม่ที่สร้างไว้ และตรวจสิทธิ์/การเชื่อมต่อก่อน
- การดึงข้อมูลจริงอาจถูกจำกัดจากเว็บไซต์ ให้หยุดเมื่อเจอ 403/429/CAPTCHA
- ทุนเป้าหมายถูกเก็บในไฟล์ requirements สำหรับการเปรียบเทียบเท่านั้น; Collector ยังคงบันทึกทุนที่เว็บไซต์เสนอจริงทั้งหมด
- เก็บไฟล์ `.env` และข้อมูลความลับไว้ในเครื่อง ไม่ Push ขึ้น GitHub

## ขั้นถัดไป
1. ตรวจ `anc_variant_screening.csv` และอนุมัติ/แก้เหตุผลที่ติด REVIEW
2. ยืนยันปีรุ่นย่อย/เครื่องยนต์จริง/ประเภทรหัสรถ และทดสอบ URL โดยตัวกรองตรงปี
3. เพิ่มผลการตรวจ CC/ปีจริงที่ยืนยันแล้วให้ rules
4. ทดสอบ 1 จังหวัด 1 รถด้วย DB แยก ก่อนขยาย 24 จังหวัด

## SQLite สำหรับเครื่องบริษัทที่ไม่มี MySQL Server

เพิ่ม Backend ชื่อ `anc_sqlite_backend.py` ใช้ `sqlite3` จาก Python โดยไม่ต้องติดตั้งฐานข้อมูล Server
และยังใช้ตาราง `anc_competitor_*_v4` ตามชื่อเดิมในไฟล์ SQLite
ระบบ MySQL เดิมยังอยู่และเป็นค่า default ถ้าไม่ระบุ `--db-backend`

### อัปเดตโค้ด (ใน PowerShell ที่ D:\WORK\anc-broker-di)

```powershell
git switch refactor-v1
git pull --ff-only origin refactor-v1
.\.venv\Scripts\python.exe -m unittest -v test_anc_requirements test_anc_sqlite
```

การทดสอบ SQLite ใช้ Temporary Directory ไม่เรียกเว็บไซต์ ไม่ต่อ MySQL และไม่แตะฐานเดิม
ต้องได้ `OK` จึงไปต่อ (ถ้ามี ERROR ให้หยุดและส่งข้อความจาก Terminal)

### ทดสอบหนึ่ง Target

เมื่อได้รับอนุญาตให้เรียกเว็บไซต์และการทดสอบผ่านแล้ว:

```powershell
.\.venv\Scripts\python.exe anc_collector.py --db-backend sqlite --sqlite-path .\anc_broker_test.sqlite3 --limit 1 --delay 3 --debug
```

โปรแกรมจะสร้าง `anc_broker_test.sqlite3` ในโฟลเดอร์ปัจจุบัน และ CSV ที่ตั้งค่าไว้
`--limit 1` เลือกเป้าหมายแรก คือ สุโขทัย / HONDA CITY / 2020; ครอบคลุมรุ่นย่อยผู้สมัครและซ่อมอู่ของ Target นี้ ไม่ใช่แค่แพ็กเกจเดียว
ผลสำเร็จขึ้นกับเว็บไซต์จริง ไม่มีการการันตีว่าจะมีข้อเสนอประกันภัยทุกชุด

### อ่านข้อมูลหลังทดลอง

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('anc_broker_test.sqlite3'); print(c.execute('select province, count(*) from anc_competitor_insurance_v4 group by province').fetchall()); print(c.execute('select status,count(*) from anc_competitor_branch_v4 group by status').fetchall()); c.close()"
```

ควรเก็บ SQLite และ WAL/SHM files ในเครื่องตามนโยบาย IT และไม่ Push ขึ้น GitHub (`.gitignore` ได้เพิ่ม pattern)
**ข้อควรทราบ** SQLite บันทึก Decimal เป็น TEXT เพื่อหลีกเลี่ยงการเสียความแม่นยำจาก Float; การวิเคราะห์ตัวเลขต้องแปลงเป็น Decimal/CAST
**ยังไม่ทดสอบ End-to-End บนเครื่องผู้ใช้** ต้องตรวจ `test_anc_sqlite` และผลจาก 1 Target ก่อนขยายงาน

## Data Quality v2 (แก้หลังทดสอบ 193 รายการ)

ปรับ `anc_collector.py` และเพิ่ม `anc_data_quality.py`, `test_anc_data_quality.py`:
- ยังคงใช้เบี้ยและทุนของ **Listing** เป็นค่าข้อเสนอ ไม่เอาค่า Detail มาแทนโดยอัตโนมัติ
- ถ้าวงเงิน Own Damage ของ Detail ไม่ตรงทุน Listing: เก็บค่าของ Detail ใน `raw_detail`; ไม่ใส่ค่า Own Damage ที่ไม่ตรงลงคอลัมน์มาตรฐาน และตั้ง `REVIEW_REQUIRED`
- ถ้าราคา Listing != Detail: คงข้อมูลสองแหล่งและตั้ง `REVIEW_REQUIRED` (เศษทศนิยมอาจเป็นการปัดเศษ ให้พิจารณารายงาน)
- การประเมิน Branch: `DETAIL_UNAVAILABLE` ไม่ใช่ Detail สำเร็จ จึงทำให้ Branch เป็น `PARTIAL` หากยังมีรายการไม่ครบ
- โหมด Resume ปกติยังไม่ยิงซ้ำรายการ `DETAIL_UNAVAILABLE` เพื่อลดการเรียกเว็บ
- หากต้องการลอง 404 ซ้ำ ให้ระบุ `--retry-unavailable` อย่างชัดเจน; อย่าตั้งค่านี้กับทั้ง 24 จังหวัดโดยไม่ทดลองก่อน
- ออกรายงาน CSV ใน `anc_audit_output/` หลัง Collector export สำเร็จ
- `anc_data_quality.py` ใช้ตรวจ CSV เดิม 193 รายการได้ทันทีแบบออฟไลน์

### ขั้นตอนทดสอบ (ไม่ต้องเรียกเว็บไซต์)
```powershell
git switch refactor-v1
git pull --ff-only origin refactor-v1
.\.venv\Scripts\python.exe -m unittest -v test_anc_requirements test_anc_sqlite test_anc_data_quality
.\.venv\Scripts\python.exe anc_data_quality.py --input .\anc_competitor_insurance_24_provinces.csv --out .\anc_audit_output
```
ไฟล์ผล:
- `anc_audit_output/anc_audit_summary.csv`: จำนวนแต่ละสถานะ/ประเด็น
- `anc_audit_output/anc_audit_review_queue.csv`: แถวที่ควรตรวจ
- `anc_audit_output/anc_audit_all.csv`: ข้อมูลทุกแถวพร้อมธง

**คำเตือน:** ข้อมูล 193 แถวใน SQLite เดิมยังมีค่า Own Damage จาก Parser เวอร์ชันก่อน
การอัปเดตโค้ด **ไม่แก้ย้อนหลังในฐานข้อมูลเดิม**; รายงานออฟไลน์จะตรวจได้จาก `raw_detail`.
อย่าลบฐาน SQLite เดิมหรือรัน `--no-resume` กับไฟล์เดิมโดยไม่สำรองข้อมูลก่อน.
การทดสอบ Unit Tests ไม่ใช่การรับรองความถูกต้องของราคา/กรมธรรม์กับเว็บไซต์จริง.

## กติกาที่ผู้ขอยืนยัน (2 พ.ย. 2569)

- เก็บ **ทุกทุนประกัน** ตามที่เว็บไซต์แสดง ไม่กรองให้ตรงทุนเป้าหมาย
- ในรายงาน `anc_audit_all.csv` มี `target_sum_insured`, `target_sum_gap_thb` (ทุนเสนอ - ทุนเป้าหมาย; บวก=สูงกว่า), `target_sum_abs_gap_thb`, `target_sum_gap_pct`, `sum_match_status`
- `coverage_own_damage` เป็นความคุ้มครองแยกจาก `actual_sum_insured`; ไม่ต้องเท่ากัน และความต่างกันอย่างเดียวไม่ใช่ข้อผิดพลาด
- `premium` จาก Listing เป็นราคาเสนอจริงที่เก็บไว้ ส่วนราคา Detail อยู่ใน `raw_detail.premium` และคอลัมน์ตรวจสอบ `detail_premium_observed`
- ยังคงตรวจ `PREMIUM_DIFF_GT_100`, URL Detail หลายทุน, ข้อมูลบริษัทที่ขาด, ข้อจำกัดจังหวัด, 404 และ RETRY
- รายงานนี้ไม่เปลี่ยนฐาน SQLite เดิม ใช้คำสั่ง `--export-only` เพื่อส่งออกข้อมูลเก่าและคำนวณคอลัมน์ใหม่ได้โดยไม่เรียกเว็บ

### วิธีรันตรวจข้อมูลเดิม (ไม่เรียกเว็บไซต์)
```powershell
git pull --ff-only origin refactor-v1
.\.venv\Scripts\python.exe -m unittest -v test_anc_requirements test_anc_sqlite test_anc_data_quality
.\.venv\Scripts\python.exe anc_data_quality.py --input .\anc_city2020_v2.csv --out .\anc_audit_v3
```
ควรตรวจ `anc_audit_v3/anc_audit_all.csv` และ `anc_audit_v3/anc_audit_summary.csv`.
ข้อจำกัด: คอลัมน์เปรียบเทียบทุนนำเสนอใช้ทุนเป้าหมายของ 20 สเปกที่กำหนด ไม่ใช่การยืนยันว่าทุนใกล้ที่สุดในเว็บไซต์ทั้งหมด และไม่ปรับเบี้ยตามสัดส่วนทุน.


## Pilot specific target index

`--target-index N` เลือกชุดจังหวัด×รถลำดับที่ N (เริ่มจาก 1) แทน `--limit`; ใช้ร่วมกันไม่ได้. เมื่อจังหวัดแรกเป็นสุโขทัย มีรถตาม TARGET_SPECS 20 รุ่น, `--target-index 11` คือ Honda City 2022 ซ่อมห้าง. ใช้ SQLite ชุดใหม่แยกทดลอง.

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_anc_target_selection
.\.venv\Scripts\python.exe anc_collector.py --db-backend sqlite --sqlite-path .\anc_pilot_dealer_city2022.sqlite3 --target-index 11 --delay 3 --output .\anc_pilot_dealer_city2022.csv
```

ตัวเลือกนี้ยังไม่ได้ยืนยันว่ารุ่นย่อยที่เว็บไซต์เสนอมีจริงสำหรับปีดังกล่าว; ต้องตรวจรายชื่อรุ่นย่อย/ปี/รหัสประกันภายหลัง.

## FULL RUN 24 จังหวัด × 20 สเปก (480 targets)

รันได้ใน PowerShell บน Windows ที่ไม่มี MySQL หรือสิทธิ์ Administrator (ต้องมี .venv ติดตั้ง dependencies เรียบร้อยแล้ว):

```powershell
git switch refactor-v1
git pull --ff-only origin refactor-v1
.\.venv\Scripts\python.exe -m unittest -v test_anc_requirements test_anc_sqlite test_anc_data_quality test_anc_target_selection
.\.venv\Scripts\python.exe anc_full_run.py --db .\anc_full_24provinces.sqlite3 --output .\anc_full_24provinces.csv --batch-size 20 --delay 3 --max-requests 18000
```

1. `anc_full_run.py` เปิด Collector ทีละชุด 20 Target รวม 480 ชุด โดยส่ง `--start-index` และ `--end-index`, SQLite เดียวกันทุกชุดและ Resume อัตโนมัติ
2. หลังแต่ละชุด Collector export CSV ทั้งฐาน + Audit อัตโนมัติใน `anc_audit_output/`; wrapper เขียน `anc_full_run/checkpoint_XXX_YYY.json` และ `batch_XXX_YYY_tryN.log`
3. หาก process ถึง HTTP budget จะหยุดด้วย exit code 75 แล้ว retry ชุดเดียวกันได้สูงสุดอีกครั้ง; หากยังถึง budget อีก จะหยุดให้ผู้ใช้ตรวจ ไม่วนไม่สิ้นสุด
4. หากโดน robots/site block (HTTP 401/403/429) จะหยุดด้วย exit code 76, **ไม่** retry ฝ่าการจำกัดเว็บไซต์
5. หาก target รายตัวล้มเหลว (เช่น ไม่มีรุ่นใน catalog) Collector บันทึก `FAILED` แล้วทำรายการถัดไป. ถ้าทั้งช่วงมีเป้าหมายล้มเหลวอย่างน้อย 80% และไม่มีข้อมูลเพิ่ม จะหยุดด้วย exit code 77 เพื่อป้องกันการรันผิดตลอดประเทศ
6. ไม่ใช่ทุกผลต้อง Detail DONE: Listing Only, URL ร่วม, ทุนต่างเป้า และชื่อแพ็กเกจพื้นที่จะเก็บตามจริงพร้อมธงตรวจ
7. ถ้าหยุดโดยกด Ctrl+C หรือเครื่องดับ ให้ใช้คำสั่งเดิมอีกครั้งเพื่อ Resume. Wrapper จะวนตั้งแต่ชุดแรก แต่ Target ที่ DONE จะถูกข้าม; Target PARTIAL อาจตรวจ Listing อีกครั้ง
8. **ห้ามเปิดสอง Collector พร้อมกันบน SQLite ชุดเดียวกัน** และอย่าคัดลอก SQLite ขณะโปรแกรมกำลังเขียน หากต้องสำรอง ให้ปิด Collector ก่อนหรือใช้ SQLite backup API
9. จำนวน 480 คือจำนวนเงื่อนไขทั้งหมด ไม่ใช่จำนวนข้อเสนอหรือจำนวนรุ่นย่อย; `COLLECT` ยังคงเป็นแค่การคัดกรองเบื้องต้นและไม่ยืนยันการเข้ารหัสรับประกันภัย 110 หรือ trim/year จริง
10. ใช้ภาพรวมสถานะ `DONE/PARTIAL/FAILED/BLOCKED/INTERRUPTED` ประกอบกับจำนวนข้อเสนอ. อย่าแปล `FAILED` ว่าไม่มีบริษัทเสนอประกันโดยอัตโนมัติ

ตรวจความคืบหน้าระหว่างรัน:
```powershell
Get-ChildItem .\anc_full_run\checkpoint_*.json | Sort-Object Name | Select-Object -Last 3
Get-Content .\anc_audit_output\anc_audit_summary.csv -TotalCount 30
```

ฐานข้อมูลใหม่ `anc_full_24provinces.sqlite3` ไม่ทับ Pilot เดิม. `--max-requests` เป็นเพดานด้านความปลอดภัยของโปรแกรม ไม่ใช่โควตาของเว็บไซต์ ควรปฏิบัติตามเงื่อนไขการเข้าถึงและนโยบายบริษัทเสมอ.
