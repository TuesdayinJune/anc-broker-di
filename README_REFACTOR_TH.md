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
