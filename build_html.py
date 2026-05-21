# -*- coding: utf-8 -*-
"""Build price-query.html with embedded price database"""
import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\user\Desktop\claude\price_db.json', encoding='utf-8') as f:
    db = json.load(f)

data_js  = json.dumps(db['records'], ensure_ascii=False)
gen_time = db['generated']
total    = db['total']

HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🌿 綠源科技 成本價格資料庫</title>
<script src="https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0d1117;--panel:#161b22;--border:#30363d;--accent:#3fb950;--accent2:#58a6ff;
  --text:#e6edf3;--text2:#8b949e;--red:#f85149;--orange:#f97316;--yellow:#d29922;
  --hover:#1c2128;--tag-bg:#21262d;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;min-height:100vh}
.topbar{background:var(--panel);border-bottom:1px solid var(--border);padding:10px 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;position:sticky;top:0;z-index:100}
.logo{font-size:16px;font-weight:800;color:var(--accent);white-space:nowrap}
.search-wrap{flex:1;min-width:200px;position:relative}
.search-wrap input{width:100%;background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:7px 12px 7px 34px;color:var(--text);font-size:13px;outline:none}
.search-wrap input:focus{border-color:var(--accent2)}
.search-ico{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text2);font-size:14px}
select{background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:12px;cursor:pointer}
.btn{border:none;border-radius:6px;padding:6px 12px;font-size:12px;cursor:pointer;font-weight:600}
.btn-primary{background:var(--accent);color:#000}
.btn-ghost{background:var(--tag-bg);color:var(--text);border:1px solid var(--border)}
.stat-chip{background:var(--tag-bg);border:1px solid var(--border);border-radius:12px;padding:3px 10px;font-size:11px;color:var(--text2)}
.stat-chip b{color:var(--accent)}
.main{display:flex;height:calc(100vh - 53px)}
.left-pane{flex:1;overflow-y:auto;min-width:0}
.right-pane{width:340px;flex-shrink:0;background:var(--panel);border-left:1px solid var(--border);overflow-y:auto;display:flex;flex-direction:column}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:#1c2128;padding:8px 10px;text-align:left;color:var(--text2);font-weight:600;border-bottom:1px solid var(--border);cursor:pointer;white-space:nowrap;position:sticky;top:0;z-index:10}
thead th:hover{color:var(--text)}
tbody tr{border-bottom:1px solid #21262d;cursor:pointer;transition:background .1s}
tbody tr:hover{background:var(--hover)}
tbody tr.active{background:#1c2844!important}
td{padding:7px 10px;vertical-align:middle}
.item-name{font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}
.tag{display:inline-block;background:var(--tag-bg);border:1px solid var(--border);border-radius:10px;padding:1px 7px;font-size:10px;color:var(--text2);white-space:nowrap}
.price{font-weight:700;font-variant-numeric:tabular-nums}
.price.sell{color:var(--accent2)}
.price.cost{color:#3fb950}
.margin{font-size:11px;font-weight:700}
.margin.hi{color:#3fb950}.margin.mid{color:#d29922}.margin.lo{color:#f85149}
.date-cell{color:var(--text2);white-space:nowrap;font-size:11px}
.proj-cell{color:var(--text2);font-size:11px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.empty{text-align:center;padding:60px 20px;color:var(--text2)}
.rpanel-section{padding:14px;border-bottom:1px solid var(--border)}
.rpanel-title{font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}
.rpanel-item-name{font-size:14px;font-weight:700;color:var(--text);margin-bottom:4px;line-height:1.3}
.rpanel-meta{font-size:11px;color:var(--text2);margin-bottom:2px}
.chart-wrap{padding:14px;flex:0 0 auto}
.chart-canvas-wrap{background:#0d1117;border:1px solid var(--border);border-radius:8px;padding:10px;height:180px}
.calc-row{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.calc-label{font-size:11px;color:var(--text2);min-width:70px}
.calc-input{background:#0d1117;border:1px solid var(--border);border-radius:5px;padding:5px 8px;color:var(--text);font-size:13px;width:100%;outline:none}
.calc-input:focus{border-color:var(--accent)}
.calc-result{background:#0d1117;border:1px solid var(--accent);border-radius:6px;padding:10px;text-align:center;margin-top:8px}
.calc-result .price-out{font-size:22px;font-weight:800;color:var(--accent)}
.calc-result .price-sub{font-size:11px;color:var(--text2);margin-top:2px}
.hist-item{padding:8px 0;border-bottom:1px solid #21262d;display:flex;justify-content:space-between;align-items:flex-start}
.hist-item:last-child{border-bottom:none}
.hist-left{flex:1;min-width:0}
.hist-proj{font-size:11px;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hist-dt{font-size:10px;color:var(--text2);opacity:.7}
.hist-right{text-align:right;flex-shrink:0;margin-left:8px}
.hist-cp{font-size:12px;font-weight:700;color:#3fb950}
.hist-sp{font-size:11px;color:#58a6ff}
.add-form{padding:14px;background:var(--panel);border-bottom:1px solid var(--border)}
.form-row{margin-bottom:8px}
.form-label{font-size:11px;color:var(--text2);margin-bottom:3px}
.form-input{width:100%;background:#0d1117;border:1px solid var(--border);border-radius:5px;padding:6px 8px;color:var(--text);font-size:12px;outline:none}
.form-input:focus{border-color:var(--accent)}
.footer-note{padding:6px 14px;font-size:10px;color:var(--text2);border-top:1px solid var(--border);margin-top:auto}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
.toast{position:fixed;bottom:20px;right:20px;background:#1c2128;border:1px solid var(--accent);border-radius:8px;padding:10px 16px;font-size:12px;color:var(--text);z-index:999;display:none}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo">🌿 成本資料庫</div>
  <div class="search-wrap">
    <span class="search-ico">🔍</span>
    <input type="text" id="searchInput" placeholder="智慧搜尋：輸入項目名稱、規格、案場、廠商…" oninput="onSearch()">
  </div>
  <select id="catFilter" onchange="onSearch()"><option value="">所有類別</option></select>
  <select id="yearFilter" onchange="onSearch()"><option value="">所有年份</option></select>
  <select id="sortSel" onchange="renderTable(filteredRecords)">
    <option value="date_desc">日期新→舊</option>
    <option value="date_asc">日期舊→新</option>
    <option value="cost_desc">成本高→低</option>
    <option value="cost_asc">成本低→高</option>
    <option value="item_asc">項目A→Z</option>
  </select>
  <button class="btn btn-ghost" onclick="toggleAdd()">＋ 新增</button>
  <button class="btn btn-ghost" onclick="exportCSV()">↓ CSV</button>
  <span class="stat-chip">共 <b id="totalCount">0</b> 筆</span>
  <span class="stat-chip" id="filterChip" style="display:none">篩選 <b id="filterCount">0</b> 筆</span>
</div>

<div class="main">
  <div class="left-pane">
    <div id="addFormWrap" class="add-form" style="display:none">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px;color:var(--accent)">＋ 手動新增</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px">
        <div class="form-row"><div class="form-label">類別</div><input class="form-input" id="f_cat" placeholder="成本分析"></div>
        <div class="form-row"><div class="form-label">項目名稱 *</div><input class="form-input" id="f_item" placeholder="電纜線"></div>
        <div class="form-row"><div class="form-label">規格</div><input class="form-input" id="f_spec" placeholder="直流 1.5kV"></div>
        <div class="form-row"><div class="form-label">單位</div><input class="form-input" id="f_unit" placeholder="kWp"></div>
        <div class="form-row"><div class="form-label">數量</div><input class="form-input" id="f_qty" type="number"></div>
        <div class="form-row"><div class="form-label">成本單價</div><input class="form-input" id="f_cost" type="number"></div>
        <div class="form-row"><div class="form-label">報價單價</div><input class="form-input" id="f_sell" type="number"></div>
        <div class="form-row"><div class="form-label">案場</div><input class="form-input" id="f_proj" placeholder="精湛光學案"></div>
        <div class="form-row"><div class="form-label">日期</div><input class="form-input" id="f_date" type="date"></div>
        <div class="form-row"><div class="form-label">廠商</div><input class="form-input" id="f_sup" placeholder="海懋"></div>
        <div class="form-row"><div class="form-label">備註</div><input class="form-input" id="f_note"></div>
      </div>
      <div style="margin-top:10px;display:flex;gap:8px">
        <button class="btn btn-primary" onclick="addRecord()">儲存</button>
        <button class="btn btn-ghost" onclick="toggleAdd()">取消</button>
      </div>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th onclick="colSort('item')">項目名稱</th>
          <th onclick="colSort('category')">類別</th>
          <th>規格/備註</th>
          <th onclick="colSort('unit')">單位</th>
          <th onclick="colSort('cost_price')">成本單價</th>
          <th onclick="colSort('sell_price')">報價單價</th>
          <th>毛利%</th>
          <th onclick="colSort('project')">案場</th>
          <th onclick="colSort('date')">日期</th>
          <th onclick="colSort('supplier')">廠商</th>
        </tr></thead>
        <tbody id="tableBody"></tbody>
      </table>
      <div id="emptyState" class="empty" style="display:none">
        <div style="font-size:36px;margin-bottom:8px">🔍</div>
        <div>找不到符合項目</div>
      </div>
    </div>
  </div>

  <div class="right-pane">
    <div id="detailPlaceholder" style="text-align:center;padding:50px 14px">
      <div style="font-size:36px;margin-bottom:10px">📊</div>
      <div style="color:var(--text2);font-size:12px">點選任一列查看<br>價格趨勢與建議售價</div>
    </div>
    <div id="detailPanel" style="display:none">
      <div class="rpanel-section">
        <div class="rpanel-title">📋 項目詳情</div>
        <div class="rpanel-item-name" id="d_name"></div>
        <div class="rpanel-meta" id="d_meta"></div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
          <span class="tag" id="d_cat"></span>
          <span class="tag" id="d_unit"></span>
        </div>
      </div>
      <div class="chart-wrap">
        <div class="rpanel-title">📈 歷史價格趨勢</div>
        <div class="chart-canvas-wrap"><canvas id="trendChart"></canvas></div>
        <div id="trendInfo" style="font-size:10px;color:var(--text2);margin-top:4px;text-align:center"></div>
      </div>
      <div class="rpanel-section">
        <div class="rpanel-title">💰 建議售價</div>
        <div class="calc-row">
          <div class="calc-label">最新成本</div>
          <div id="c_cost" style="flex:1;font-size:14px;font-weight:700;color:#3fb950">—</div>
        </div>
        <div class="calc-row">
          <div class="calc-label">毛利率</div>
          <input class="calc-input" id="c_margin" type="number" value="30" min="0" max="99" oninput="calcSuggest()">
          <span style="color:var(--text2);font-size:12px">%</span>
        </div>
        <div class="calc-result">
          <div class="price-out" id="c_suggest">—</div>
          <div class="price-sub">建議售價（含 <span id="c_mLabel">30</span>% 毛利）</div>
        </div>
        <div id="c_yoy" style="margin-top:8px;font-size:10px;color:var(--text2)"></div>
      </div>
      <div class="rpanel-section" style="flex:1">
        <div class="rpanel-title">📁 所有紀錄 <span id="histCount" style="font-weight:400"></span></div>
        <div id="histList"></div>
      </div>
    </div>
    <div class="footer-note" id="footerNote"></div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
/* ── Data ── */
const BASE_DB = __PRICE_DATA__;

let manualRecs = [];
try { manualRecs = JSON.parse(localStorage.getItem('pricedb_manual')||'[]'); } catch(e){}

let allRecs = [...BASE_DB, ...manualRecs];
let filtered = [...allRecs];
let selectedRec = null;
let trendChart = null;
let sortCol = 'date', sortDir = 'desc';

/* ── Init ── */
function init(){
  document.getElementById('totalCount').textContent = allRecs.length;
  document.getElementById('footerNote').textContent =
    '資料庫更新：__GEN_TIME__ ｜ 共 __TOTAL__ 筆（含手動 '+manualRecs.length+' 筆）';

  const cats = [...new Set(allRecs.map(r=>r.category).filter(Boolean))].sort();
  const cs = document.getElementById('catFilter');
  cats.forEach(c=>{ const o=document.createElement('option'); o.value=c; o.textContent=c; cs.appendChild(o); });

  const yrs = [...new Set(allRecs.map(r=>r.date?r.date.slice(0,4):'').filter(Boolean))].sort().reverse();
  const ys = document.getElementById('yearFilter');
  yrs.forEach(y=>{ const o=document.createElement('option'); o.value=y; o.textContent=y+'年'; ys.appendChild(o); });

  onSearch();
}

/* ── Fuse ── */
let fuse = null;
function mkFuse(){ return new Fuse(allRecs,{keys:['item','spec','project','supplier','category','note'],threshold:0.35,includeScore:true,minMatchCharLength:1}); }

function onSearch(){
  const q   = document.getElementById('searchInput').value.trim();
  const cat = document.getElementById('catFilter').value;
  const yr  = document.getElementById('yearFilter').value;

  let res = allRecs;
  if(q.length>=1){ if(!fuse) fuse=mkFuse(); res=fuse.search(q).map(r=>r.item); }
  if(cat) res=res.filter(r=>r.category===cat);
  if(yr)  res=res.filter(r=>r.date&&r.date.startsWith(yr));

  filtered = res;
  renderTable(filtered);

  const chip=document.getElementById('filterChip');
  if(q||cat||yr){ chip.style.display=''; document.getElementById('filterCount').textContent=res.length; }
  else chip.style.display='none';
}

function colSort(f){
  if(sortCol===f) sortDir=sortDir==='asc'?'desc':'asc';
  else{ sortCol=f; sortDir='desc'; }
  renderTable(filtered);
}

/* ── Table ── */
function renderTable(recs){
  const tbody=document.getElementById('tableBody');
  const empty=document.getElementById('emptyState');
  if(!recs.length){ tbody.innerHTML=''; empty.style.display=''; return; }
  empty.style.display='none';

  const sorted=[...recs].sort((a,b)=>{
    let av=a[sortCol]??'', bv=b[sortCol]??'';
    if(av<bv) return sortDir==='desc'?1:-1;
    if(av>bv) return sortDir==='desc'?-1:1;
    return 0;
  });

  tbody.innerHTML=sorted.slice(0,500).map((r,i)=>{
    const cost=r.cost_price?fmt(r.cost_price):'—';
    const sell=r.sell_price?fmt(r.sell_price):'—';
    const mg=r.cost_price&&r.sell_price?Math.round((r.sell_price-r.cost_price)/r.sell_price*100):null;
    const mc=mg===null?'':mg>=30?'hi':mg>=15?'mid':'lo';
    const ns=[r.spec,r.note].filter(Boolean).join(' | ')||'—';
    return `<tr onclick="selectRow(${i})" id="row_${i}">
      <td><div class="item-name" title="${x(r.item)}">${x(r.item)}</div></td>
      <td><span class="tag">${x(r.category||'—')}</span></td>
      <td style="color:var(--text2);font-size:11px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${x(ns)}">${x(ns)}</td>
      <td style="color:var(--text2)">${x(r.unit||'—')}</td>
      <td><span class="price cost">${cost}</span></td>
      <td><span class="price sell">${sell}</span></td>
      <td><span class="margin ${mc}">${mg===null?'—':mg+'%'}</span></td>
      <td class="proj-cell" title="${x(r.project||'')}">${x(r.project||'—')}</td>
      <td class="date-cell">${r.date?r.date.slice(0,7):'—'}</td>
      <td style="color:var(--text2);font-size:11px">${x(r.supplier||'—')}</td>
    </tr>`;
  }).join('');
}

function fmt(n){ return n==null?'—':Math.round(n).toLocaleString('zh-TW'); }
function x(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

/* ── Detail panel ── */
function selectRow(i){
  document.querySelectorAll('tbody tr').forEach(tr=>tr.classList.remove('active'));
  const tr=document.getElementById('row_'+i); if(tr) tr.classList.add('active');
  const r=filtered[i]; if(!r) return;
  selectedRec=r; showDetail(r);
}

function showDetail(r){
  document.getElementById('detailPlaceholder').style.display='none';
  document.getElementById('detailPanel').style.display='';
  document.getElementById('d_name').textContent=r.item;
  document.getElementById('d_meta').textContent=[r.spec,r.note].filter(Boolean).join(' · ')||(r.project?'案場：'+r.project:'');
  document.getElementById('d_cat').textContent=r.category||'—';
  document.getElementById('d_unit').textContent=(r.unit?r.unit+'計':'');

  // Similar items
  const key=r.item.slice(0,5);
  const similar=allRecs.filter(x=>x.item===r.item||x.item.includes(key)||r.item.includes(x.item.slice(0,5)))
    .filter(x=>x.cost_price||x.sell_price)
    .sort((a,b)=>(a.date||'')>(b.date||'')?1:-1);

  buildChart(similar);
  buildHist(similar);
  updateCalc(r, similar);
}

function buildChart(recs){
  if(trendChart){ trendChart.destroy(); trendChart=null; }
  const pts=recs.filter(x=>x.date).sort((a,b)=>a.date>b.date?1:-1);
  document.getElementById('trendInfo').textContent=pts.length+'筆歷史紀錄';
  if(!pts.length) return;
  trendChart=new Chart(document.getElementById('trendChart'),{
    type:'line',
    data:{
      labels:pts.map(x=>x.date.slice(0,7)),
      datasets:[
        {label:'成本',data:pts.map(x=>x.cost_price||null),borderColor:'#3fb950',backgroundColor:'#3fb95022',pointRadius:4,tension:.3,spanGaps:true},
        {label:'報價',data:pts.map(x=>x.sell_price||null),borderColor:'#58a6ff',backgroundColor:'#58a6ff11',pointRadius:4,tension:.3,spanGaps:true}
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{legend:{labels:{color:'#8b949e',font:{size:10}},position:'top'},
               tooltip:{callbacks:{label:c=>c.dataset.label+': NT$'+Math.round(c.raw||0).toLocaleString()}}},
      scales:{
        x:{ticks:{color:'#8b949e',font:{size:9},maxTicksLimit:6},grid:{color:'#21262d'}},
        y:{ticks:{color:'#8b949e',font:{size:9},callback:v=>'$'+v.toLocaleString()},grid:{color:'#21262d'}}
      }
    }
  });
}

function buildHist(recs){
  const el=document.getElementById('histList');
  document.getElementById('histCount').textContent='('+recs.length+'筆)';
  if(!recs.length){ el.innerHTML='<div style="color:var(--text2);font-size:11px">無記錄</div>'; return; }
  el.innerHTML=[...recs].reverse().map(r=>{
    const cs=r.cost_price?'NT$'+fmt(r.cost_price)+(r.unit?'/'+r.unit:''):'';
    const ss=r.sell_price?'NT$'+fmt(r.sell_price):'';
    return `<div class="hist-item">
      <div class="hist-left"><div class="hist-proj">${x(r.project||r.source||'—')}</div>
        <div class="hist-dt">${r.date||'—'}${r.supplier?' · '+r.supplier:''}</div></div>
      <div class="hist-right">
        ${cs?`<div class="hist-cp">${cs}</div>`:''}
        ${ss?`<div class="hist-sp">報 ${ss}</div>`:''}
      </div></div>`;
  }).join('');
}

function updateCalc(r, similar){
  const latest=[...similar].filter(x=>x.cost_price).sort((a,b)=>a.date>b.date?-1:1)[0];
  const cost=latest?.cost_price||r.cost_price;
  document.getElementById('c_cost').textContent=cost
    ?'NT$'+fmt(cost)+(latest?.unit?'/'+latest.unit:''):'無成本資料';

  if(similar.filter(x=>x.cost_price).length>=2){
    const s=similar.filter(x=>x.cost_price&&x.date).sort((a,b)=>a.date>b.date?1:-1);
    const old=s[0], nw=s[s.length-1];
    if(old!==nw&&old.cost_price){
      const chg=((nw.cost_price-old.cost_price)/old.cost_price*100).toFixed(1);
      document.getElementById('c_yoy').textContent=
        old.date?.slice(0,7)+' NT$'+fmt(old.cost_price)+' → '+nw.date?.slice(0,7)+' NT$'+fmt(nw.cost_price)+
        ' ('+(chg>0?'↑':'↓')+Math.abs(chg)+'%)';
    }
  } else document.getElementById('c_yoy').textContent='';
  calcSuggest();
}

function calcSuggest(){
  if(!selectedRec) return;
  const latest=[...allRecs].filter(x=>x.item===selectedRec.item&&x.cost_price)
    .sort((a,b)=>a.date>b.date?-1:1)[0];
  const cost=latest?.cost_price||selectedRec.cost_price;
  if(!cost){ document.getElementById('c_suggest').textContent='—'; return; }
  const m=parseFloat(document.getElementById('c_margin').value)||30;
  document.getElementById('c_suggest').textContent='NT$'+Math.round(cost/(1-m/100)).toLocaleString();
  document.getElementById('c_mLabel').textContent=m;
}

/* ── Add ── */
function toggleAdd(){
  const w=document.getElementById('addFormWrap');
  w.style.display=w.style.display==='none'?'':'none';
}
function addRecord(){
  const item=document.getElementById('f_item').value.trim();
  if(!item){ showToast('請輸入項目名稱'); return; }
  const r={
    category:document.getElementById('f_cat').value.trim()||'其他',
    item, spec:document.getElementById('f_spec').value.trim(),
    unit:document.getElementById('f_unit').value.trim(),
    qty:parseFloat(document.getElementById('f_qty').value)||null,
    cost_price:parseFloat(document.getElementById('f_cost').value)||null,
    sell_price:parseFloat(document.getElementById('f_sell').value)||null,
    project:document.getElementById('f_proj').value.trim(),
    date:document.getElementById('f_date').value,
    supplier:document.getElementById('f_sup').value.trim(),
    source:'手動輸入',
    note:document.getElementById('f_note').value.trim(),
  };
  manualRecs.push(r);
  localStorage.setItem('pricedb_manual',JSON.stringify(manualRecs));
  allRecs=[...BASE_DB,...manualRecs]; fuse=null;
  document.getElementById('totalCount').textContent=allRecs.length;
  toggleAdd(); onSearch();
  showToast('✅ 已新增：'+item);
  ['f_cat','f_item','f_spec','f_unit','f_qty','f_cost','f_sell','f_proj','f_date','f_sup','f_note']
    .forEach(id=>document.getElementById(id).value='');
}

/* ── Export ── */
function exportCSV(){
  const recs=filtered.length?filtered:allRecs;
  const hdr=['類別','項目名稱','規格','單位','數量','成本單價','報價單價','毛利%','案場','日期','廠商','來源','備註'];
  const rows=recs.map(r=>{
    const m=r.cost_price&&r.sell_price?Math.round((r.sell_price-r.cost_price)/r.sell_price*100):'';
    return [r.category,r.item,r.spec,r.unit,r.qty,r.cost_price,r.sell_price,m,r.project,r.date,r.supplier,r.source,r.note]
      .map(v=>typeof v==='string'&&v.includes(',')?'"'+v+'"':v??'').join(',');
  });
  const csv='﻿'+[hdr.join(','),...rows].join('\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  a.download='綠源成本資料庫_'+new Date().toISOString().slice(0,10)+'.csv';
  a.click(); showToast('✅ 已匯出 '+recs.length+' 筆');
}

function showToast(msg){
  const t=document.getElementById('toast'); t.textContent=msg; t.style.display='block';
  setTimeout(()=>t.style.display='none',2500);
}

init();
</script>
</body></html>"""

# Inject data
HTML = HTML.replace('__PRICE_DATA__', data_js)
HTML = HTML.replace('__GEN_TIME__', gen_time)
HTML = HTML.replace('__TOTAL__', str(total))

with open(r'C:\Users\user\Desktop\claude\price-query.html', 'w', encoding='utf-8') as f:
    f.write(HTML)

size = os.path.getsize(r'C:\Users\user\Desktop\claude\price-query.html')
print(f'Done! price-query.html = {size//1024} KB')
