"""
ESS Dashboard 後端 API
執行: python app.py
預設 Port: 5050
"""

import os, json, time, logging
import requests as _req
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

from gms_client import get_client
from thingnario_client import get_thingnario_client
from ipvita_client import get_ipvita_client, parse_site_data as ipvita_parse
from solaredge_client import fetch_all as se_fetch_all
from line_notifier import send_alert, send_alert_summary, send_resolved, send_test as line_send_test

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app   = Flask(__name__)
CORS(app)  # 允許前端 HTML 跨域呼叫

PORT           = int(os.getenv("PORT", 5050))
CACHE_MINUTES  = int(os.getenv("CACHE_MINUTES", 60))
CACHE_FILE     = Path(__file__).parent / "cache.json"
CWA_KEY        = os.getenv("CWA_KEY", "")

# CWA 縣市別名（前端用「台」，CWA 用「臺」）
_COUNTY_ALIAS = {
    "台南市":"臺南市","台東縣":"臺東縣",
    "台北市":"臺北市","台中市":"臺中市",
}
_wx_cache: dict = {}       # county → {wx, temp, min_t, max_t}
_wx_cache_ts: dict = {}    # county → float

# ── GMS 案場對照表（名稱 → GMS plantNO）────────────────────────
PLANT_MAP: dict[str, str] = {
    "東培龍潭":  "BDL222060124",   # id=12, cap=1279.46 kWp
    "屏東客運":  "BDL222060166",   # id=19, cap=1571.39 kWp
}

# ── iPVita 案場對照表（名稱 → iPVita site code）─────────────────
IPVITA_SITE_MAP: dict[str, str] = {
    "大量科技": "PTW02115",   # 東元旭能(大量科技)，桃園八德，667.23 kWp
}

# ── Thingnario 案場對照表（名稱 → Thingnario plantNo）──────────
THINGNARIO_PLANT_MAP: dict[str, str] = {
    "恩智浦廠一期":       "GST001-1-2",   # 高雄楠梓, 702 kWp
    "東元觀音二廠(高壓)": "GST003",        # 桃園觀音, 809 kWp
    "東元觀音二廠(低壓)": "GST003-1",      # 桃園觀音, 203 kWp
    "東元湖口廠":         "GST004",        # 新竹湖口, 1811 kWp
    "台以八翁一期":       "GST005",        # 台南柳營, 62 kWp
    "板橋果菜市場":       "GST006",        # 新北板橋, 208 kWp
}

# ── 快取 ─────────────────────────────────────────────────────
_cache: dict = {}
_cache_time: float = 0

# ── 告警狀態追蹤（避免重複推播）─────────────────────────────
# key = site_name, value = alert_num（上次已推播的筆數）
_notified_alerts: dict[str, int] = {}

def load_cache():
    global _cache, _cache_time
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            _cache      = data.get("data", {})
            _cache_time = data.get("time", 0)
            logger.info("載入快取 (%d 筆)", len(_cache))
        except Exception:
            pass

def save_cache():
    CACHE_FILE.write_text(
        json.dumps({"time": time.time(), "data": _cache}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def is_cache_valid():
    return (time.time() - _cache_time) < (CACHE_MINUTES * 60)


# ── 主要資料拉取 ──────────────────────────────────────────────
def fetch_all_sites():
    """定時任務：從 GMS + Thingnario 拉取所有案場即時數據"""
    updated = 0

    # ── GMS 資料源 ───────────────────────────────────
    try:
        gms = get_client()
        plants = gms.get_plant_list()
        today = date.today().isoformat()
        plant_data = {p["plantNo"]: p for p in plants}
        for site_name, plant_no in PLANT_MAP.items():
            if plant_no in plant_data:
                p = plant_data[plant_no]
                ac_kw = p.get("ac_kw") or 0
                cap   = p.get("capacity") or 1
                today_kwh = round(ac_kw * 6, 1)
                _cache[site_name] = {
                    "today_kwh":  today_kwh,
                    "month_kwh":  0,
                    "total_kwh":  0,
                    "days7":      [today_kwh] * 7,
                    "efficiency": round(ac_kw / cap, 3),
                    "ac_kw":      ac_kw,
                    "radiation":  p.get("radiation", 0),
                    "wind_speed": p.get("wind_speed"),
                    "kw_pr":      p.get("kw_pr", 0),
                    "mod_temp":   p.get("mod_temp"),
                    "amb_temp":   p.get("amb_temp"),
                    "alert_num":  p.get("alert_num"),
                    "alert_flag": p.get("alert_flag", ""),
                    "collected":  p.get("collected", ""),
                    "updated":    today,
                }
                logger.info("✓ GMS %s: %.1f kW", site_name, ac_kw)
                updated += 1

                try:
                    from firebase_client import push_gms_alert, resolve_gms_alert
                    alert_num_val = int(p.get("alert_num") or 0)
                    if alert_num_val > 0:
                        push_gms_alert(site_name, alert_num_val)
                    else:
                        resolve_gms_alert(site_name)
                except Exception as fb_err:
                    logger.warning("Firebase 推送跳過: %s", fb_err)
            else:
                logger.warning("✗ GMS %s (plantNO=%s) 不在清單中", site_name, plant_no)
    except Exception as e:
        logger.error("fetch_all_sites (GMS) 例外: %s", e)

    # ── Thingnario 資料源 ─────────────────────────────
    if THINGNARIO_PLANT_MAP:
        try:
            tn = get_thingnario_client()
            for site_name, plant_no in THINGNARIO_PLANT_MAP.items():
                data = tn.fetch_realtime(plant_no)
                if data:
                    _cache[site_name] = data
                    logger.info("✓ Thingnario %s (%s): %.1f kW, 今日 %.1f kWh",
                                site_name, plant_no, data["ac_kw"], data["today_kwh"])
                    updated += 1
                else:
                    logger.warning("✗ Thingnario %s (%s) 無資料", site_name, plant_no)
        except Exception as e:
            logger.error("fetch_all_sites (Thingnario) 例外: %s", e)

    # ── iPVita 資料源（大量科技）─────────────────────────────
    if IPVITA_SITE_MAP:
        try:
            iv = get_ipvita_client()
            iv_sites = {s["site"]: s for s in iv.fetch_all_sites()}
            for site_name, site_id in IPVITA_SITE_MAP.items():
                raw = iv_sites.get(site_id)
                if raw:
                    _cache[site_name] = ipvita_parse(raw)
                    d = _cache[site_name]
                    logger.info("✓ iPVita %s (%s): %.1f kW, 今日 %.1f kWh",
                                site_name, site_id, d["ac_kw"], d["today_kwh"])
                    updated += 1
                else:
                    logger.warning("✗ iPVita %s (%s) 無資料", site_name, site_id)
        except Exception as e:
            logger.error("fetch_all_sites (iPVita) 例外: %s", e)

    # ── SolarEdge 資料源（Playwright 瀏覽器登入）────────────────
    try:
        se_sites = se_fetch_all()
        for d in se_sites:
            site_name = d.pop("site_name")
            d.pop("site_id", None)
            _cache[site_name] = d
            logger.info("✓ SolarEdge %s: 今日 %.1f kWh, 告警 %d",
                        site_name, d["today_kwh"], d["alert_num"])
        updated += len(se_sites)
    except Exception as e:
        logger.error("fetch_all_sites (SolarEdge) 例外: %s", e)

    save_cache()
    logger.info("快取更新完成 (%d 案場)", updated)

    # ── 推送即時數據到 Firestore（供前端直接讀取）──────────────
    try:
        from firebase_client import push_site_realtime
        for site_name, data in _cache.items():
            push_site_realtime(site_name, data)
        logger.info("✓ Firestore site_realtime 同步完成 (%d 案場)", len(_cache))
    except Exception as fb_err:
        logger.warning("Firestore site_realtime 推送跳過: %s", fb_err)

    # ── LINE 通知改為「每天定時兩次」推播（見 send_daily_alert_digest）──
    # 不再每次抓取就推播，避免洗版＆節省免費額度（每月 200 則）。
    # 排程在 09:00 與 16:00 各推一次當前所有案場告警總覽。


# ── 定時告警總覽推播（每天 09:00 / 16:00）──────────────────────
def send_daily_alert_digest():
    """推播當前所有案場的告警總覽到 LINE。固定時間呼叫，不做去重。"""
    alerts = []
    for site_name, data in _cache.items():
        alert_num = int(data.get("alert_num") or 0)
        if alert_num > 0:
            level = "critical" if alert_num >= 3 else "warning"
            alerts.append({
                "site":      site_name,
                "level":     level,
                "alert_num": alert_num,
                "detail":    f"目前有 {alert_num} 筆異常",
            })

    if alerts:
        ok = send_alert_summary(alerts)
        logger.info("定時告警總覽推播：%d 案場 異常，結果=%s", len(alerts), ok)
    else:
        # 全部正常也推一則，當作系統心跳，讓使用者確認通知管道正常
        from line_notifier import _token, _group_id
        import requests as _r
        token, gid = _token(), _group_id()
        if token and gid:
            text = ("✅ ESS 戰情版｜定時巡檢\n"
                    "━━━━━━━━━━━━━━━\n"
                    "目前所有案場運作正常，無告警。")
            try:
                r = _r.post("https://api.line.me/v2/bot/message/push",
                            headers={"Content-Type": "application/json",
                                     "Authorization": f"Bearer {token}"},
                            json={"to": gid, "messages": [{"type": "text", "text": text}]},
                            timeout=8)
                logger.info("定時告警總覽推播：全部正常，HTTP=%d", r.status_code)
            except Exception as e:
                logger.error("定時推播例外: %s", e)


# ── API 路由 ──────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "cache_sites": len(_cache),
        "cache_age_min": round((time.time() - _cache_time) / 60, 1),
        "plant_map_count": len(PLANT_MAP),
    })


@app.get("/api/discover")
def discover():
    """
    自動探索 GMS 上的案場清單，回傳 plantNO 列表。
    用來找出各案場的 plantNO，填入 PLANT_MAP。
    """
    try:
        client = get_client()
        plants = client.get_plant_list()
        return jsonify({"ok": True, "count": len(plants), "plants": plants})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/sites")
def get_sites():
    """回傳所有案場的快取監控數據"""
    if not is_cache_valid() and PLANT_MAP:
        fetch_all_sites()
    return jsonify({
        "ok":      True,
        "count":   len(_cache),
        "updated": date.today().isoformat(),
        "data":    _cache,
    })


@app.get("/api/site/<path:site_name>")
def get_site(site_name: str):
    """回傳單一案場的監控數據（path 參數支援帶/的名稱）"""
    from urllib.parse import unquote
    name = unquote(site_name)

    if name in _cache:
        return jsonify({"ok": True, "data": _cache[name]})

    # 先查 iPVita
    iv_site_id = IPVITA_SITE_MAP.get(name)
    if iv_site_id:
        try:
            iv  = get_ipvita_client()
            raw = iv.fetch_site(iv_site_id)
            if raw:
                _cache[name] = ipvita_parse(raw)
                save_cache()
                return jsonify({"ok": True, "data": _cache[name]})
        except Exception as e:
            logger.warning("iPVita 即時查詢 %s 失敗: %s", name, e)

    # 再查 Thingnario
    tn_plant_no = THINGNARIO_PLANT_MAP.get(name)
    if tn_plant_no:
        try:
            tn   = get_thingnario_client()
            data = tn.fetch_realtime(tn_plant_no)
            if data:
                _cache[name] = data
                save_cache()
                return jsonify({"ok": True, "data": data})
        except Exception as e:
            logger.warning("Thingnario 即時查詢 %s 失敗: %s", name, e)

    # 再查 GMS
    plant_no = PLANT_MAP.get(name)
    if not plant_no:
        return jsonify({"ok": False, "error": f"找不到 {name} 的 plantNO，請更新 PLANT_MAP 或 THINGNARIO_PLANT_MAP"}), 404

    try:
        client = get_client()
        data   = client.fetch_realtime(plant_no)
        if data is None:
            return jsonify({"ok": False, "error": f"GMS 未回傳 {name} 的數據"}), 502

        data["updated"] = date.today().isoformat()
        _cache[name] = data
        save_cache()
        return jsonify({"ok": True, "data": _cache[name]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/refresh")
def refresh():
    """手動強制更新所有案場數據"""
    fetch_all_sites()
    return jsonify({"ok": True, "sites_updated": len(_cache)})


@app.get("/api/plant-map")
def get_plant_map():
    return jsonify({"ok": True, "plant_map": PLANT_MAP, "thingnario_plant_map": THINGNARIO_PLANT_MAP})


@app.get("/api/thingnario/discover")
def thingnario_discover():
    """列出 Thingnario 帳號下的所有案場"""
    try:
        tn = get_thingnario_client()
        plants = tn.get_plant_list()
        return jsonify({"ok": True, "count": len(plants), "plants": [
            {"plantNo": p["plantNo"], "plantName": p["plantName"],
             "totalCapacity": p.get("totalCapacity"), "regionNo": p.get("regionNo")}
            for p in plants
        ]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/thingnario/site/<path:plant_no>")
def thingnario_site(plant_no: str):
    """直接用 Thingnario plantNo 查詢即時數據"""
    try:
        tn = get_thingnario_client()
        data = tn.fetch_realtime(plant_no)
        if data is None:
            return jsonify({"ok": False, "error": f"無法取得 {plant_no} 的數據"}), 502
        return jsonify({"ok": True, "plantNo": plant_no, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/plant-map")
def update_plant_map():
    """
    動態更新 PLANT_MAP，Body: {"天賜良園": "PLANT_NO", ...}
    """
    updates = request.get_json(force=True) or {}
    PLANT_MAP.update(updates)
    return jsonify({"ok": True, "plant_map": PLANT_MAP})


# ── LINE API ──────────────────────────────────────────────────

@app.post("/api/line/webhook")
def line_webhook():
    """
    LINE Messaging API Webhook。
    Bot 在群組收到任何訊息時，自動回覆群組的 group_id。
    """
    body = request.get_json(silent=True) or {}
    token = os.getenv("LINE_TOKEN", "")

    for event in body.get("events", []):
        src       = event.get("source", {})
        src_type  = src.get("type", "")
        reply_tok = event.get("replyToken", "")

        if src_type == "group":
            gid = src.get("groupId", "")
            logger.info("LINE group_id 偵測到: %s", gid)
            print(f"\n>>> LINE_GROUP_ID={gid}  請複製到 .env <<<\n", flush=True)

            # 自動回覆 group_id 到群組內
            if reply_tok and token:
                _requests = __import__("requests")
                _requests.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    json={
                        "replyToken": reply_tok,
                        "messages": [{
                            "type": "text",
                            "text": f"✅ ESS Bot 已就緒\n群組 ID：\n{gid}\n\n請將此 ID 複製到後端 .env 的 LINE_GROUP_ID"
                        }]
                    },
                    timeout=5,
                )

    return "", 200


@app.get("/api/line/test")
def line_test():
    """發送測試訊息到 LINE 群組，確認 token 和 group_id 設定正確"""
    result = line_send_test()
    status = 200 if result["ok"] else 400
    return jsonify(result), status


# ── 告警 API ──────────────────────────────────────────────────

@app.get("/api/alerts")
def get_alerts():
    """從快取中整合所有有告警的案場，回傳告警清單"""
    import datetime as _dt
    now = _dt.datetime.now()
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    alerts = []
    for site_name, data in _cache.items():
        alert_num = int(data.get("alert_num") or 0)
        alert_flag = str(data.get("alert_flag") or "")
        if alert_num > 0:
            level = "critical" if alert_num >= 3 else "warning"
            alerts.append({
                "id":        f"gms_{site_name}",
                "level":     level,
                "icon":      "🔴" if level == "critical" else "🟡",
                "site":      site_name,
                "title":     "GMS 監控告警",
                "detail":    f"目前有 {alert_num} 筆異常（{alert_flag}），請至 GMS 平台確認",
                "time":      time_str,
                "date":      today,
                "source":    "gms",
                "alert_num": alert_num,
            })

    return jsonify({"ok": True, "count": len(alerts), "alerts": alerts})


@app.get("/api/gms/alerts/<path:site_name>")
def get_gms_site_alerts(site_name: str):
    """
    從 GMS 取得指定案場的告警明細清單。
    僅支援 PLANT_MAP 中已設定的 GMS 案場。
    """
    from urllib.parse import unquote
    name = unquote(site_name)
    plant_no = PLANT_MAP.get(name)
    if not plant_no:
        return jsonify({
            "ok": False,
            "error": f"此案場 ({name}) 不在 GMS PLANT_MAP 中，無法查詢告警明細",
            "alerts": [],
        }), 404

    try:
        client = get_client()
        raw_alerts = client.fetch_device_alerts(plant_no)
        # 標準化欄位（GMS 回傳格式未知，盡量通吃）
        normalized = []
        for a in raw_alerts:
            if isinstance(a, dict):
                normalized.append({
                    "device":   a.get("DeviceName") or a.get("device_name") or a.get("Name") or a.get("name") or "—",
                    "type":     a.get("AlertType")  or a.get("alert_type")  or a.get("Type") or a.get("type") or "—",
                    "status":   a.get("Status")     or a.get("status")      or a.get("State") or "—",
                    "desc":     a.get("Description")or a.get("desc")        or a.get("Desc") or a.get("message") or "—",
                    "time":     a.get("AlertTime")  or a.get("alert_time")  or a.get("Time") or a.get("time") or "—",
                    "level":    a.get("Level")      or a.get("level")       or a.get("Severity") or "—",
                    "_raw":     a,  # 保留原始資料方便除錯
                })
        return jsonify({
            "ok":       True,
            "site":     name,
            "plant_no": plant_no,
            "count":    len(normalized),
            "alerts":   normalized,
        })
    except Exception as e:
        logger.error("GMS 告警明細查詢失敗 %s: %s", name, e)
        return jsonify({"ok": False, "error": str(e), "alerts": []}), 500


# ── 氣象局 API ────────────────────────────────────────────────
WX_TTL = 1800  # 30 分鐘快取

def _wx_emoji(desc: str) -> str:
    if "雷" in desc:       return "⛈"
    if "大雨" in desc or "豪雨" in desc: return "🌧"
    if "雨" in desc:       return "🌦"
    if "霧" in desc:       return "🌫"
    if "雪" in desc:       return "❄️"
    if "陰" in desc and "雨" not in desc: return "☁️"
    if "多雲" in desc:     return "⛅"
    if "晴" in desc:       return "☀️"
    return "🌤"

@app.get("/api/weather/<path:city>")
def get_weather(city: str):
    from urllib.parse import unquote
    city = unquote(city)
    cwa_city = _COUNTY_ALIAS.get(city, city)

    # 快取命中
    if city in _wx_cache and time.time() - _wx_cache_ts.get(city, 0) < WX_TTL:
        return jsonify({"ok": True, "data": _wx_cache[city], "cached": True})

    if not CWA_KEY:
        return jsonify({"ok": False, "error": "CWA_KEY 未設定"}), 503

    try:
        r = _req.get(
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001",
            params={
                "Authorization": CWA_KEY,
                "locationName": cwa_city,
                "elementName": "Wx,MinT,MaxT",
            },
            timeout=8,
            verify=False,   # 台灣政府憑證在 Windows 需停用驗證
        )
        r.raise_for_status()
        locations = r.json()["records"]["location"]
        if not locations:
            return jsonify({"ok": False, "error": f"找不到縣市: {cwa_city}"}), 404

        elements = {e["elementName"]: e["time"] for e in locations[0]["weatherElement"]}
        wx_desc = elements["Wx"][0]["parameter"]["parameterName"]
        min_t   = int(elements["MinT"][0]["parameter"]["parameterName"])
        max_t   = int(elements["MaxT"][0]["parameter"]["parameterName"])
        # 白天用 max，傍晚後用 min（以14點為界）
        hour = date.today().timetuple().tm_hour if False else time.localtime().tm_hour
        temp = max_t if 7 <= hour < 18 else min_t

        data = {
            "city":  city,
            "wx":    wx_desc,
            "emoji": _wx_emoji(wx_desc),
            "temp":  temp,
            "min_t": min_t,
            "max_t": max_t,
        }
        _wx_cache[city]    = data
        _wx_cache_ts[city] = time.time()
        logger.info("天氣 %s: %s %d°C (%d~%d)", city, wx_desc, temp, min_t, max_t)
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        logger.error("CWA 天氣查詢失敗 (%s): %s", city, e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 啟動 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    load_cache()

    # 定時每 CACHE_MINUTES 分鐘自動刷新
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_all_sites, "interval", minutes=CACHE_MINUTES, id="refresh")
    # 每天 09:00、16:00 各推一次 LINE 告警總覽（使用系統本地時間＝台灣時間）
    scheduler.add_job(send_daily_alert_digest, "cron", hour=9,  minute=0, id="digest_am")
    scheduler.add_job(send_daily_alert_digest, "cron", hour=16, minute=0, id="digest_pm")
    scheduler.start()
    logger.info("排程啟動：每 %d 分鐘更新；LINE 告警總覽 09:00 / 16:00", CACHE_MINUTES)

    # 啟動時立即拉一次（若 PLANT_MAP 已設定）
    if PLANT_MAP:
        fetch_all_sites()
    else:
        logger.info("PLANT_MAP 尚未設定，請先呼叫 GET /api/discover 取得案場清單")

    logger.info("API 伺服器啟動: http://localhost:%d", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)
