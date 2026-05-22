# -*- coding: utf-8 -*-
"""Patch 綠源報價資料庫_完整版.html: add edit modal + batch-delete source"""
import sys, re, os
sys.stdout.reconfigure(encoding='utf-8')

IN  = r"C:\Users\user\Desktop\claude\綠源報價資料庫_完整版.html"
OUT = r"C:\Users\user\Desktop\claude\綠源報價資料庫_完整版.html"

with open(IN, encoding='utf-8') as f:
    html = f.read()

# ── 1. Extra CSS ──────────────────────────────────────────────────────
extra_css = """
.edit{padding:3px 8px;font-size:11px;border:1px solid #c8b400;border-radius:4px;color:#7a6200;cursor:pointer;background:#fff;flex-shrink:0}
.edit:hover{background:#fff8e0}
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:#fff;border-radius:10px;padding:22px 24px;width:min(520px,95vw);max-height:90vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.2)}
.modal h3{font-size:15px;font-weight:600;margin-bottom:14px}
.modal-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
.mg label{display:block;font-size:11px;color:#666;margin-bottom:3px}
.mg input,.mg select{width:100%;padding:6px 9px;font-size:13px;border:1px solid #d0d0c8;border-radius:5px;outline:none}
.mg input:focus,.mg select:focus{border-color:#c8b400}
.mg.full{grid-column:1/-1}
.modal-footer{display:flex;justify-content:space-between;align-items:center;margin-top:14px;gap:8px}
.sbtn-x{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;font-size:10px;border:1px solid #e0c0b8;border-radius:99px;cursor:pointer;background:#fff;color:#c84800;margin-left:2px;line-height:1;flex-shrink:0;vertical-align:middle}
.sbtn-x:hover{background:#fff0ee}
"""
html = html.replace('.del:hover{background:#fff0ee}', '.del:hover{background:#fff0ee}' + extra_css)

# ── 2. Modal HTML + toast (replace existing toast, insert modal before </body>) ──
# Remove existing toast div if present
html = html.replace('<div class="toast" id="toast"></div>', '')

modal_html = """
<!-- Edit Modal -->
<div class="modal-overlay" id="edit-modal">
  <div class="modal">
    <h3>✏️ 編輯資料</h3>
    <div class="modal-grid">
      <div class="mg full"><label>品名 / 規格</label><input id="e-name" type="text"></div>
      <div class="mg"><label>成本單價 (NT$)</label><input id="e-price" type="number" step="0.01" min="0"></div>
      <div class="mg"><label>單位</label><input id="e-unit" type="text" placeholder="式/m/只/套…"></div>
      <div class="mg"><label>供應商</label><input id="e-supplier" type="text"></div>
      <div class="mg"><label>日期 (YYYY/MM)</label><input id="e-date" type="text" placeholder="2025/06"></div>
      <div class="mg"><label>類別</label>
        <select id="e-cat">
          <option>其他</option><option>線材電纜</option><option>配電盤</option><option>逆變器</option>
          <option>管材線槽</option><option>變壓器</option><option>顧問服務</option><option>工班工資</option>
          <option>太陽能模組</option><option>管材類</option><option>保險安衛</option><option>支架鋼構</option>
          <option>監控系統</option><option>電氣設備</option><option>監控設備</option><option>NFB開關</option>
          <option>消防設備</option><option>安全設施</option><option>UPS</option><option>ACB開關</option>
          <option>配管工程</option><option>HVE</option><option>開關設備</option><option>電錶儀器</option><option>CPO</option>
        </select>
      </div>
      <div class="mg full"><label>來源 / 案場名稱（可直接修改為正確案名）</label><input id="e-source" type="text"></div>
    </div>
    <div class="modal-footer">
      <button class="btn" style="color:#c84800;border-color:#e0c0b8" onclick="delFromModal()">🗑 刪除此筆</button>
      <div style="display:flex;gap:8px">
        <button class="btn" onclick="closeModal()">取消</button>
        <button class="btn btn-p" onclick="saveEdit()">儲存</button>
      </div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
"""
html = html.replace('</body>', modal_html + '</body>')

# ── 3. Card: add 編 button ────────────────────────────────────────────
old_del = """  <button class="del" onclick="del('${item.id}')">刪</button>"""
new_del = """  <button class="edit" onclick="openEdit(event,'${item.id}')">編</button>
  <button class="del" onclick="del('${item.id}')">刪</button>"""
html = html.replace(old_del, new_del)

# ── 4. Source buttons: add × batch-delete ────────────────────────────
old_src = r"""Object.entries(srcCounts).sort((a,b)=>b[1]-a[1]).map(([s,n])=>
      `<button class="sbtn ${activeSrc===s?'on':''}" onclick="setSrc('${s.replace(/'/g,"\\'")}',this)">${s} (${n})</button>`
    ).join('');"""

new_src = r"""Object.entries(srcCounts).sort((a,b)=>b[1]-a[1]).map(([s,n])=>{
      const se = s.replace(/'/g,"\\'");
      return `<span style="display:inline-flex;align-items:center"><button class="sbtn ${activeSrc===s?'on':''}" onclick="setSrc('${se}',this)">${s} (${n})</button><button class="sbtn-x" title="整批刪除此來源" onclick="delSrc('${se}')">&times;</button></span>`;
    }).join('');"""

html = html.replace(old_src, new_src)

# ── 5. New JS functions ───────────────────────────────────────────────
new_js = r"""
// ── Edit / Delete functions ─────────────────────────────────────────
let editId = null;

function openEdit(e, id) {
  e.stopPropagation();
  const item = db.find(i => i.id === id);
  if (!item) return;
  editId = id;
  document.getElementById('e-name').value     = item.name     || '';
  document.getElementById('e-price').value    = item.price    || '';
  document.getElementById('e-unit').value     = item.unit     || '';
  document.getElementById('e-supplier').value = item.supplier || '';
  document.getElementById('e-date').value     = item.date     || '';
  document.getElementById('e-source').value   = item.source   || '';
  const sel = document.getElementById('e-cat');
  sel.value = item.category || '其他';
  document.getElementById('edit-modal').classList.add('open');
}

function closeModal() {
  document.getElementById('edit-modal').classList.remove('open');
  editId = null;
}

function saveEdit() {
  if (!editId) return;
  const idx = db.findIndex(i => i.id === editId);
  if (idx < 0) return;
  db[idx].name     = document.getElementById('e-name').value.trim();
  db[idx].price    = parseFloat(document.getElementById('e-price').value) || 0;
  db[idx].unit     = document.getElementById('e-unit').value.trim();
  db[idx].supplier = document.getElementById('e-supplier').value.trim();
  db[idx].date     = document.getElementById('e-date').value.trim();
  db[idx].source   = document.getElementById('e-source').value.trim();
  db[idx].category = document.getElementById('e-cat').value;
  save(); renderStats(); render();
  document.getElementById('hdr-count').textContent = db.length + ' 筆資料';
  closeModal();
  toast('✅ 已儲存');
}

function delFromModal() {
  if (!editId) return;
  if (!confirm('確定刪除這筆資料？')) return;
  db = db.filter(i => i.id !== editId);
  save(); renderStats(); render();
  document.getElementById('hdr-count').textContent = db.length + ' 筆資料';
  closeModal();
  toast('已刪除');
}

function delSrc(src) {
  const count = db.filter(i => i.source === src).length;
  if (!confirm('確定刪除「' + src + '」的 ' + count + ' 筆資料？此操作無法復原。')) return;
  db = db.filter(i => i.source !== src);
  if (activeSrc === src) activeSrc = 'all';
  save(); renderStats(); render();
  document.getElementById('hdr-count').textContent = db.length + ' 筆資料';
  toast('已刪除 ' + count + ' 筆');
}

// Close modal when clicking overlay background
document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('edit-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
  });
});
"""
html = html.replace('</script>', new_js + '</script>')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Done!  {os.path.getsize(OUT)//1024} KB")
