"""
SolarEdge 監控平台客戶端（Playwright 瀏覽器登入）
繞過 Cloudflare，帳號密碼登入，撈取所有案場即時資料
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_URL  = "https://monitoring.solaredge.com"
EMAIL     = os.getenv("SOLAREDGE_EMAIL",    "peter.chen@greensource-tech.com")
PASSWORD  = os.getenv("SOLAREDGE_PASSWORD", "peter@28696141")

# 案場 ID → 中文名稱（對照 searchSites 結果）
SITE_NAMES: dict[int, str] = {
    3486956: "苗栗揚展",           # 前端 id:26
    2343786: "台東-東職二期",       # 前端 id:7
    2683141: "台東海端-廣源幼兒園", # 前端 id:10
      931707: "盛餘太陽能",         # 前端 id:27
    1611848: "東山1342",            # 前端 id:28
    3414139: "大林薯光案",          # 前端 id:30
    1353971: "通霄套房",            # 前端 id:29
    2762512: "花蓮-聖若瑟",         # 前端 id:4
    2762513: "花蓮-保祿",           # 前端 id:8
    2342368: "台東-東職一期",       # 前端 id:16
    2683182: "台東海端-廣源國小",   # 前端 id:15
}


async def _fetch_with_playwright() -> list[dict]:
    """
    用 Playwright 登入 SolarEdge，回傳所有案場整合後的資料清單。
    每個元素格式符合 ESS Dashboard 規格。
    """
    from playwright.async_api import async_playwright

    intercepted: dict[str, object] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # 攔截案場列表和測量值
        async def handle_response(response):
            url = response.url
            if "searchSites" in url:
                try:
                    intercepted["sites"] = await response.json()
                except Exception:
                    pass
            elif "sitesMeasurements" in url:
                try:
                    intercepted["measurements"] = await response.json()
                except Exception:
                    pass

        page.on("response", handle_response)

        # 前往登入頁
        logger.info("SolarEdge: 前往登入頁...")
        await page.goto(f"{BASE_URL}/solaredge-web/p/login", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 按 Log in 按鈕
        await page.click('a:has-text("Log in"), button:has-text("Log in")')
        await page.wait_for_timeout(3000)

        # 填寫帳密
        await page.wait_for_selector('input[type="email"], input[name="username"]', timeout=10000)
        await page.fill('input[type="email"], input[name="username"]', EMAIL)
        await page.fill('input[type="password"]', PASSWORD)
        await page.click('button[type="submit"]')

        logger.info("SolarEdge: 等待登入完成...")
        await page.wait_for_timeout(6000)
        logger.info("SolarEdge: 登入後 URL = %s", page.url)

        # 若沒自動進入案場列表，主動導覽
        if "site-list" not in page.url and "one" not in page.url:
            await page.goto(f"{BASE_URL}/one#/site-list", wait_until="networkidle")
            await page.wait_for_timeout(5000)

        # 等待資料被攔截
        for _ in range(20):
            if "sites" in intercepted and "measurements" in intercepted:
                break
            await page.wait_for_timeout(500)

        await browser.close()

    if "sites" not in intercepted or "measurements" not in intercepted:
        logger.error("SolarEdge: 未攔截到案場資料")
        return []

    return _parse(intercepted["sites"], intercepted["measurements"])


def _parse(sites_raw: dict, meas_raw: list) -> list[dict]:
    """合併 searchSites + sitesMeasurements → ESS Dashboard 格式"""
    meas_map = {m["solarFieldId"]: m for m in meas_raw}
    result = []

    for s in sites_raw.get("page", []):
        sid  = s["solarFieldId"]
        m    = meas_map.get(sid, {})
        name = SITE_NAMES.get(sid) or s.get("name", str(sid))

        today_kwh  = m.get("energyToday") or 0
        total_kwh  = m.get("energyLifeTime") or 0
        cap        = s.get("peakPower") or 1
        # 注意：SolarEdge 的 alertsCount 是「告警清單開啟中的項目數」(含歷史/低優先)，
        # 與案場總覽「無警示」不符，不能當作實際異常數。改保留為參考欄位，不當告警。
        alert_items = s.get("alertsCount") or 0
        lrt        = m.get("lastReportingTime") or ""
        pr_today   = m.get("prToday")

        result.append({
            "site_id":    sid,
            "site_name":  name,
            "today_kwh":  round(today_kwh, 2),
            "month_kwh":  round(m.get("energyMonthly") or 0, 2),
            "total_kwh":  round(total_kwh, 2),
            "days7":      [round(today_kwh, 1)] * 7,
            "efficiency": round(today_kwh / cap, 3) if cap else 0,
            "ac_kw":      0,
            "radiation":  0,
            "wind_speed": None,
            "kw_pr":      round(pr_today, 3) if pr_today else 0,
            "mod_temp":   None,
            "amb_temp":   None,
            "alert_num":  0,          # 不用 alertsCount 當異常（與平台不符）
            "alert_flag": "",
            "alert_items": alert_items,  # 保留 SolarEdge 記錄的告警項目數供參考
            "collected":  lrt,
            "updated":    lrt[:10] if lrt else "",
        })

    logger.info("SolarEdge: 解析完成，共 %d 個案場", len(result))
    return result


def fetch_all() -> list[dict]:
    """同步封裝，供 app.py 呼叫"""
    try:
        # Windows 預設 ProactorEventLoop 支援 subprocess（Playwright 需要）
        # SelectorEventLoop 不支援 subprocess，不可切換
        return asyncio.run(_fetch_with_playwright())
    except Exception as e:
        logger.error("SolarEdge fetch_all 例外: %s", e, exc_info=True)
        return []
