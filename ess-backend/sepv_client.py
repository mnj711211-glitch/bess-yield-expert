"""
SEPV solarV4 監控平台 — 登入並抓取案場發電資料
登入頁 https://www.sepv.com.tw/solarV4/id_login.aspx 為 ASP.NET WebForms，
用 requests 帶 __VIEWSTATE 登入後，site_list.aspx 一次回傳所有案場資料。
"""
import os
import re
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

BASE = "https://www.sepv.com.tw/solarV4"

# SEPV 案場名稱 → 儀表板既有案場名稱（接到現有案場，避免重複顯示）
NAME_MAP = {
    "台南柳營．牛舍（綠源施工）":       "柳營-黃燕良牛舍",
    "台南楠西．楠西（一）":            "台南/楠西一",
    "雲林西螺．雞舍（綠源合作案）":     "西螺-洪慶堂雞舍",
}

# 不納入（Test 案件、或已由其他平台提供真實資料的重複案場）
SKIP_NAMES = {
    "台南安平．天賜良緣（綠源／Test案件／追日)",
    "台南安平．天賜良緣（綠源／Test案件／固定)",
    "嘉義大林．台糖薯光案（追日案）",
}


def _num(x):
    x = (x or "").strip().replace(",", "")
    try:
        return float(x)
    except ValueError:
        return None


def fetch_sepv_sites() -> list[dict]:
    """
    登入 SEPV 並回傳所有案場的快取格式資料 list[dict]。
    site_list.aspx 欄位：ID｜案場名稱｜建置容量(kWp)｜即時發電(kW)｜今日發電(度)｜日照能量(kWh/kWp)｜…用電
    帳密未設定或登入失敗時回傳空 list。
    """
    account  = os.getenv("SEPV_ACCOUNT", "")
    password = os.getenv("SEPV_PASSWORD", "")
    if not account or not password:
        logger.info("SEPV_ACCOUNT/SEPV_PASSWORD 未設定，跳過 SEPV")
        return []

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"{BASE}/id_login.aspx",
    })
    login_url = f"{BASE}/id_login.aspx"

    try:
        r = s.get(login_url, timeout=20)

        def hidden(name: str) -> str:
            m = re.search(r'id="%s"[^>]*value="([^"]*)"' % name, r.text)
            return m.group(1) if m else ""

        s.post(login_url, data={
            "__VIEWSTATE":          hidden("__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": hidden("__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION":    hidden("__EVENTVALIDATION"),
            "txtId":    account,
            "txtIdPwd": password,
            "btnCommit.x": "20",
            "btnCommit.y": "10",
        }, timeout=20)

        html = s.get(f"{BASE}/site_list.aspx", timeout=20).text
    except Exception as e:
        logger.error("SEPV 登入/抓取失敗: %s", e)
        return []

    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")
    result = []

    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "default.aspx?hid=" not in row:
            continue
        mh = re.search(r"hid=(\d+)", row)
        if not mh or mh.group(1) == "0":
            continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        cells = [c for c in cells if c != ""]
        if len(cells) < 5:
            continue

        name  = cells[1]
        if name in SKIP_NAMES:
            continue
        name = NAME_MAP.get(name, name)   # 接到現有案場名稱
        cap   = _num(cells[2])
        ac_kw = _num(cells[3])
        today = _num(cells[4])
        yld   = _num(cells[5]) if len(cells) > 5 else None

        today = today or 0
        eff = yld if yld is not None else (round(today / cap, 3) if (today and cap) else 0)

        result.append({
            "site_name":  name,
            "today_kwh":  round(today, 2),
            "month_kwh":  0,
            "total_kwh":  0,
            "days7":      [round(today, 1)] * 7,
            "efficiency": eff,
            "ac_kw":      round(ac_kw, 2) if ac_kw is not None else 0,
            "radiation":  0,
            "wind_speed": None,
            "kw_pr":      0,
            "mod_temp":   None,
            "amb_temp":   None,
            "alert_num":  None,
            "alert_flag": "",
            "collected":  now,
            "updated":    today_str,
        })

    logger.info("SEPV: 解析完成，共 %d 個案場", len(result))
    return result
