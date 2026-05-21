# -*- coding: utf-8 -*-
"""
綠源科技 — PDF 報價單價格萃取器
支援格式：
  A. 海懋貿易  : 廠牌/規格/數量/單位/單價/總金額
  B. 標準表格  : 項次/項目說明/單位/數量/單價/金額
  C. 勁鋼/推進 : text 文字行解析 (序號 品名 規格 ...)
  D. 監控/土建 : 項目/名稱規範/單位/數量/單價/複價
輸出：追加至 price_db.json
"""
import os, sys, json, re
from datetime import datetime
import pdfplumber

sys.stdout.reconfigure(encoding='utf-8')

PDF_ROOT = r"C:\Users\user\Desktop\成本分析表"
OUT_JSON = r"C:\Users\user\Desktop\claude\price_db.json"

# ── 工具函式 ───────────────────────────────────────────────────────────
def to_num(s):
    if s is None: return None
    s = re.sub(r'[$,＄，\s]', '', str(s).strip())
    try: return float(s)
    except: return None

def parse_date_from_filename(fname):
    m = re.search(r'(\d{8})', fname)
    if m:
        s = m.group(1)
        if s[:3] in [str(y) for y in range(110, 120)]:
            return f"{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}"
        if s[:4] in [str(y) for y in range(2020, 2030)]:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    m = re.search(r'(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})', fname)
    if m: return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return ""

def get_supplier_from_name(fname):
    """從檔名抽取廠商名稱"""
    suppliers = ['海懋','大瀚','勁鋼','推進','劦孚','緻揚','鴻銘','吉發','東雲',
                 '淀鋼','成川','錡瑞','章任','達亨','聯祥','士嶺','世新','展國',
                 '永鴻','日出','午騰','沃橋','協技','丁基','天崇','穩鑽','新蘋果',
                 '永鋮','永致','泰安','華城','士電','威社','宏立','光晟','慧景',
                 '中國信託','太平洋','大亞','華新','南亞','史陶比爾']
    fname_no_ext = os.path.splitext(fname)[0]
    for s in suppliers:
        if s in fname_no_ext:
            return s
    return ""

def get_project_from_name(fname):
    """從檔名抽取案場名稱"""
    # Remove date prefix, supplier names, common suffixes
    name = re.sub(r'^\d{6,8}[_ ]*', '', fname)
    name = re.sub(r'報價單[^_]*', '', name)
    name = re.sub(r'(回簽|用印|議價|追加|修正|Final|OK).*', '', name, flags=re.IGNORECASE)
    # Extract project keywords
    proj_patterns = [
        r'([一-鿿]{2,8}案)',      # XX案
        r'([一-鿿]{2,6}廠)',      # XX廠
        r'([一-鿿]{2,8}光儲)',    # XX光儲
        r'([一-鿿]{2,8}儲能)',    # XX儲能
        r'(AP\d+[A-Z]*)',                 # AP6B etc
    ]
    for pat in proj_patterns:
        m = re.search(pat, name)
        if m: return m.group(1)
    # Try extracting words between underscores
    parts = re.split(r'[_\s]+', name)
    # Skip known supplier names
    known = ['海懋','大瀚','勁鋼','推進','劦孚','緻揚','鴻銘','華新','大亞','太平洋',
             '綠源','綠源科技','報價','報價單','回簽','用印']
    meaningful = [p for p in parts if p and p not in known and len(p) >= 2]
    return meaningful[0] if meaningful else ""

FOLDER_CATEGORY = {
    '電線電纜':      '電線電纜',
    '鋼構支架':      '鋼構支架',
    '高低壓盤':      '高低壓盤/變壓器',
    '土建':          '土建工程',
    '線槽':          '線槽',
    '監控':          '監控系統',
    '勞安':          '勞安/保險',
    '保險':          '保險',
    '圍籬':          '安全設施',
    '維修步道':      '安全設施',
    '爬梯':          '安全設施',
    '雜項':          '雜項工程',
    '跑件':          '跑件',
    '儲能':          '儲能工程',
}

def get_folder_category(filepath):
    parts = filepath.replace('\\', '/').split('/')
    for p in parts:
        for k, v in FOLDER_CATEGORY.items():
            if k in p: return v
    return '其他'

# ── 格式 A：海懋 廠牌/規格/數量/單位/單價/總金額 ─────────────────────
def parse_haimo(table, meta):
    """海懋報價單 table 格式"""
    records = []
    # Find header row
    hdr_idx = None
    for i, row in enumerate(table):
        cells = [str(c).strip() if c else '' for c in row]
        if '規格' in cells and ('單價' in cells or '單位' in cells):
            hdr_idx = i
            break
    if hdr_idx is None: return records

    hdr = [str(c).strip() if c else '' for c in table[hdr_idx]]
    def ci(*keys):
        for k in keys:
            for i, h in enumerate(hdr):
                if k in h: return i
        return None
    c_brand = ci('廠牌', '品名', '品牌')
    c_spec  = ci('規格', '型號')
    c_qty   = ci('數量')
    c_unit  = ci('單位')
    c_price = ci('單價')

    if c_price is None: return records

    for row in table[hdr_idx+1:]:
        cells = [str(c).strip() if c else '' for c in row]
        if not any(cells): continue
        price = to_num(cells[c_price] if c_price < len(cells) else None)
        if not price: continue

        brand = cells[c_brand] if c_brand is not None and c_brand < len(cells) else ''
        spec  = cells[c_spec]  if c_spec  is not None and c_spec  < len(cells) else ''
        qty   = to_num(cells[c_qty] if c_qty is not None and c_qty < len(cells) else None)
        unit  = cells[c_unit]  if c_unit  is not None and c_unit  < len(cells) else ''

        item = ' '.join(filter(None, [brand, spec])).strip() or spec or brand
        if not item: continue

        records.append({**meta, 'item': item, 'spec': spec, 'unit': unit, 'qty': qty,
                        'cost_price': price, 'sell_price': None})
    return records

# ── 格式 B：標準表格 項次/項目/單位/數量/單價/金額 ────────────────────
def parse_standard_table(table, meta):
    records = []
    hdr_idx = None
    for i, row in enumerate(table):
        cells = [str(c or '').strip() for c in row]
        joined = ' '.join(cells)
        if ('單價' in joined or '單 價' in joined) and ('數量' in joined or '名稱' in joined):
            hdr_idx = i
            break
    if hdr_idx is None: return records

    hdr = [str(c or '').strip().replace('\n', '').replace(' ', '') for c in table[hdr_idx]]
    def ci(*keys):
        for k in keys:
            for i, h in enumerate(hdr):
                if k in h: return i
        return None
    c_item  = ci('名稱', '項目', '品名', '工程項目', '說明')
    c_qty   = ci('數量')
    c_unit  = ci('單位')
    c_price = ci('單價')
    c_note  = ci('備註')

    if c_item is None or c_price is None: return records

    for row in table[hdr_idx+1:]:
        cells = [str(c or '').strip() for c in row]
        if not any(cells): continue
        item  = cells[c_item]  if c_item  < len(cells) else ''
        price = to_num(cells[c_price] if c_price < len(cells) else None)
        if not item or not price: continue
        # Skip subtotals / totals
        if any(kw in item for kw in ['總價', '合計', '稅金', '未稅', '含稅', '小計']): continue
        # Clean item name (remove leading numbers)
        item = re.sub(r'^[\d\.]+\s*', '', item).strip()
        if not item: continue

        qty  = to_num(cells[c_qty]  if c_qty  is not None and c_qty  < len(cells) else None)
        unit = cells[c_unit] if c_unit is not None and c_unit < len(cells) else ''
        note = cells[c_note] if c_note is not None and c_note < len(cells) else ''

        records.append({**meta, 'item': item, 'spec': note, 'unit': unit, 'qty': qty,
                        'cost_price': price, 'sell_price': None})
    return records

# ── 格式 C：文字行解析 (勁鋼、推進等)  ─────────────────────────────────
def parse_text_lines(text, meta):
    records = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Find header line
    hdr_line_idx = None
    for i, l in enumerate(lines):
        if re.search(r'品名|品 名|名稱', l) and re.search(r'單價|單 價', l):
            hdr_line_idx = i
            break
    if hdr_line_idx is None: return records

    # Parse subsequent lines for item rows
    # Pattern: optional_number, item_name, spec, unit?, qty, price, amount
    item_pattern = re.compile(
        r'(\d{4})\s*'                    # sequence number
        r'([一-鿿\w\-\(\)]+(?:\s+[一-鿿\w\-\(\)]+)*)\s+'  # item name
        r'(?:(.*?)\s+)?'                 # optional spec
        r'([個支組套式PCS片m米M條公尺]+)\s*'  # unit
        r'(\d+(?:\.\d+)?)\s+'            # qty
        r'\$?([\d,\.]+)\s+'              # price
        r'\$?([\d,\.]+)',                # total
        re.UNICODE
    )

    # Simpler approach: look for lines with prices
    price_line = re.compile(r'(\$[\d,\.]+|\d{3,}[\d,]*)\s*$')

    i = hdr_line_idx + 1
    while i < len(lines):
        l = lines[i]
        # Skip headers/footers
        if any(kw in l for kw in ['總計', '合計', '稅金', '銀行', '備註', '付款', '本報價', '客戶簽']):
            i += 1; continue

        # Try structured match first
        m = re.search(r'(\d{4})\s*([一-鿿\w\-\/\(\)\*]+(?:[\s\*×][一-鿿\w\-\/\(\)\*]+)*)', l)
        price_m = re.search(r'\$([\d,\.]+(?:\.\s*\d+)?)\s', l)

        if m and price_m:
            item_raw = m.group(2).strip()
            price    = to_num(price_m.group(1))
            if price and price > 0 and item_raw:
                # Try to extract spec (everything between item and unit)
                unit_m = re.search(r'\s([個支組套式PCS片m米M條公尺T]+)\s+(\d+)', l)
                unit = unit_m.group(1) if unit_m else ''
                qty  = to_num(unit_m.group(2)) if unit_m else None
                records.append({**meta, 'item': item_raw, 'spec': '', 'unit': unit,
                                'qty': qty, 'cost_price': price, 'sell_price': None})
        i += 1
    return records

# ── 格式 D：從各頁表格自動偵測 ────────────────────────────────────────
def parse_any_table(table, meta):
    """嘗試所有已知格式"""
    if not table or not table[0]: return []
    cols = [str(c or '').strip() for c in table[0]]
    cols_joined = ' '.join(cols)

    # Detect format
    if '廠牌' in cols_joined or '規格' in cols_joined:
        r = parse_haimo(table, meta)
        if r: return r

    r = parse_standard_table(table, meta)
    return r

# ── 主流程 ────────────────────────────────────────────────────────────
def process_pdf(filepath):
    fname    = os.path.basename(filepath)
    date_str = parse_date_from_filename(fname)
    supplier = get_supplier_from_name(fname)
    project  = get_project_from_name(fname)
    category = get_folder_category(filepath)

    meta = dict(category=category, spec='', unit='', qty=None,
                cost_price=None, sell_price=None,
                project=project, date=date_str, supplier=supplier,
                source=fname, note='', item='')

    records = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                # Try table extraction first
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        r = parse_any_table(table, meta)
                        records.extend(r)

                # If no records from tables, try text
                if not records:
                    text = page.extract_text() or ''
                    if len(text) > 200:
                        r = parse_text_lines(text, meta)
                        records.extend(r)
    except Exception as e:
        pass  # Scanned or unreadable PDF

    # Clean up: remove items without price, dedupe
    clean = [r for r in records if r.get('item') and r.get('cost_price') and r['cost_price'] > 0]
    return clean

# ── Run via subprocess (real kill on timeout) ─────────────────────────
import subprocess

PDF_TIMEOUT = 20  # seconds per PDF
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pdf_worker.py')

print("掃描所有 PDF 報價單...", file=sys.stderr)

all_pdf_records = []
file_count = success_count = skip_count = 0

for root, dirs, files in os.walk(PDF_ROOT):
    for fname in sorted(files):
        if not fname.endswith('.pdf'): continue
        if fname.startswith('~'): continue
        filepath = os.path.join(root, fname)
        file_count += 1
        folder = os.path.basename(root)
        try:
            result = subprocess.run(
                [sys.executable, WORKER, filepath],
                capture_output=True, text=True, encoding='utf-8',
                timeout=PDF_TIMEOUT
            )
            if result.returncode == 0 and result.stdout.strip():
                recs = json.loads(result.stdout)
                if recs:
                    success_count += 1
                    all_pdf_records.extend(recs)
                    print(f"  {len(recs):3d}筆  [{folder}] {fname}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            skip_count += 1
            print(f"  ⏱ 超時跳過  [{folder}] {fname}", file=sys.stderr)
        except Exception as e:
            skip_count += 1
            print(f"  ✗ 錯誤跳過  [{folder}] {fname}  ({e})", file=sys.stderr)

print(f"\n✅ 成功解析 {success_count}/{file_count} 個PDF，共 {len(all_pdf_records)} 筆  (跳過 {skip_count} 個)", file=sys.stderr)

# ── Merge with existing JSON ───────────────────────────────────────────
with open(OUT_JSON, encoding='utf-8') as f:
    existing = json.load(f)

existing_sources = {r['source'] for r in existing['records']}
new_recs = [r for r in all_pdf_records if r['source'] not in existing_sources]

# Add all PDF records (replace old PDF records to avoid dupes)
xlsx_recs = [r for r in existing['records'] if not r['source'].endswith('.pdf')]
merged = xlsx_recs + all_pdf_records

print(f"合併後：Excel {len(xlsx_recs)}筆 + PDF {len(all_pdf_records)}筆 = {len(merged)}筆", file=sys.stderr)

out = {
    "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "total": len(merged),
    "records": merged
}

with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"✅ 已更新 {OUT_JSON}", file=sys.stderr)
