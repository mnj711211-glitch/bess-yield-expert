"""
Thingnario (platform-api.thingnario.com) 資料擷取模組
API base: https://platform-api.thingnario.com/om/lb/api
"""

import os, time, logging
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

API_BASE    = "https://platform-api.thingnario.com/om/lb/api"
TN_EMAIL    = os.getenv("TN_EMAIL", "")
TN_PASSWORD = os.getenv("TN_PASSWORD", "")

HEADERS = {
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":       "application/json",
    "Content-Type": "application/json",
}

# Token TTL = 7 天（604800 秒），提前 1 小時刷新
_TOKEN_REFRESH_MARGIN = 3600


class ThingnarioClient:
    def __init__(self):
        self.session    = requests.Session()
        self.session.headers.update(HEADERS)
        self._token     = ""
        self._token_exp = 0.0   # unix timestamp

    # ── 認證 ─────────────────────────────────────────
    def login(self) -> bool:
        try:
            r = self.session.post(
                f"{API_BASE}/Users/login",
                json={"email": TN_EMAIL, "password": TN_PASSWORD},
                timeout=15,
            )
            if r.status_code == 201:
                data = r.json()
                self._token     = data["id"]
                ttl             = data.get("ttl", 604800)
                self._token_exp = time.time() + ttl - _TOKEN_REFRESH_MARGIN
                self.session.headers["Authorization"] = f"bearer {self._token}"
                logger.info("Thingnario 登入成功 (userId=%s)", data.get("userId"))
                return True
            logger.error("Thingnario 登入失敗: %s %s", r.status_code, r.text[:200])
            return False
        except Exception as e:
            logger.error("Thingnario 登入例外: %s", e)
            return False

    def ensure_logged_in(self):
        if not self._token or time.time() >= self._token_exp:
            if not self.login():
                raise RuntimeError("無法登入 Thingnario，請確認帳密 (TN_EMAIL / TN_PASSWORD)")

    # ── 案場清單 ─────────────────────────────────────
    def get_plant_list(self) -> list[dict]:
        """回傳帳號下所有 SolarPlants"""
        self.ensure_logged_in()
        r = self.session.get(f"{API_BASE}/SolarPlants", timeout=20)
        r.raise_for_status()
        plants = r.json()
        logger.info("Thingnario 取得案場清單: %d 筆", len(plants))
        return plants

    # ── 即時概覽 ─────────────────────────────────────
    def get_plant_overview(self, plant_no: str) -> dict:
        """
        取得案場即時狀態
        回傳: {ac_kw, irradiance, temperature, shortStatus}
        """
        self.ensure_logged_in()
        r = self.session.get(
            f"{API_BASE}/SolarPlants/getSinglePlantOverview",
            params={"plantNo": plant_no},
            timeout=15,
        )
        r.raise_for_status()
        live = r.json().get("live", {})
        return {
            "ac_kw":       live.get("plant_output_kw") or live.get("sum_inv_output_kw") or 0,
            "irradiance":  live.get("irradiance", 0),
            "mod_temp":    live.get("meter_temperature"),
            "shortStatus": live.get("shortStatus", "Unknown"),
        }

    # ── 發電量 ───────────────────────────────────────
    def get_energy(self, plant_no: str, start: str, end: str) -> float:
        """
        取得指定日期範圍的發電量 (kWh)。
        start / end 格式: "YYYY-MM-DD"
        注意: end 要比 start 多至少 1 天（API 限制）。
        """
        self.ensure_logged_in()
        r = self.session.get(
            f"{API_BASE}/SolarPlants/{plant_no}/EnergySystemAnalytics",
            params={"start": start, "end": end},
            timeout=20,
        )
        if r.status_code != 200:
            logger.warning("get_energy %s [%s~%s] 失敗: %s", plant_no, start, end, r.text[:100])
            return 0.0
        return float(r.json().get("pvKwh", 0))

    # ── 逐日發電量 (7天) ─────────────────────────────
    def get_days7(self, plant_no: str) -> list[float]:
        """回傳最近 7 天每日發電量 (kWh)，最後一筆為今日（部分）"""
        today = date.today()
        result = []
        for i in range(6, -1, -1):
            d_start = (today - timedelta(days=i)).isoformat()
            d_end   = (today - timedelta(days=i - 1)).isoformat()
            kwh = self.get_energy(plant_no, d_start, d_end)
            result.append(round(kwh, 1))
        return result

    # ── 進行中事件（告警明細）─────────────────────────
    def get_active_events(self, plant_no: str) -> dict | None:
        """
        取得案場「進行中」(未結束) 事件摘要。
        回傳: {device, code, type, category, message, started, count} 或 None。
        """
        import json as _json
        self.ensure_logged_in()
        try:
            r = self.session.get(
                f"{API_BASE}/SolarEvents/findOne",
                params={"filter": _json.dumps({
                    "where": {"plantNo": plant_no, "endTimestamp": None},
                    "order": "startTimestamp DESC",
                })},
                timeout=12,
            )
            if r.status_code != 200:
                return None
            ev = r.json()
            if not ev:
                return None

            # 進行中事件數
            rc = self.session.get(
                f"{API_BASE}/SolarEvents/count",
                params={"where": _json.dumps({"plantNo": plant_no, "endTimestamp": None})},
                timeout=12,
            )
            count = rc.json().get("count", 0) if rc.status_code == 200 else 0

            # 事件訊息文字對照
            message, category = "", ""
            mid = ev.get("eventMessageId")
            if mid:
                rm = self.session.get(f"{API_BASE}/SolarEventMessages/{mid}", timeout=12)
                if rm.status_code == 200:
                    m = rm.json()
                    message  = m.get("message") or m.get("description") or ""
                    category = m.get("category") or ""

            return {
                "device":   ev.get("deviceNo", ""),
                "code":     ev.get("value", ""),
                "type":     ev.get("eventType", ""),
                "category": category,
                "message":  message,
                "started":  ev.get("startTimestamp", ""),
                "count":    count,
            }
        except Exception as e:
            logger.warning("Thingnario get_active_events(%s) 例外: %s", plant_no, e)
            return None

    # ── 完整即時數據（供後端快取使用）───────────────
    def fetch_realtime(self, plant_no: str) -> dict | None:
        """
        整合即時 + 當日 + 月度發電量。
        回傳格式與 GMS client 相容（today_kwh, month_kwh, days7, ac_kw …）
        """
        try:
            today     = date.today()
            tomorrow  = (today + timedelta(days=1)).isoformat()
            m_start   = today.strftime("%Y-%m-01")

            ov        = self.get_plant_overview(plant_no)
            today_kwh = self.get_energy(plant_no, today.isoformat(), tomorrow)
            month_kwh = self.get_energy(plant_no, m_start, tomorrow)
            days7     = self.get_days7(plant_no)

            return {
                "today_kwh":  round(today_kwh, 1),
                "month_kwh":  round(month_kwh, 1),
                "total_kwh":  0,            # Thingnario 不提供累積電量
                "days7":      days7,
                "efficiency": round(today_kwh / max(ov["ac_kw"], 1), 3) if ov["ac_kw"] else 0,
                "ac_kw":      round(ov["ac_kw"], 3),
                "irradiance": ov["irradiance"],
                "mod_temp":   ov["mod_temp"],
                "amb_temp":   None,
                "wind_speed": None,
                "kw_pr":      0,
                "alert_num":  0 if ov["shortStatus"] == "Normal" else 1,
                "alert_flag": ov["shortStatus"],
                "collected":  today.isoformat(),
                "updated":    today.isoformat(),
            }
        except Exception as e:
            logger.error("Thingnario fetch_realtime(%s) 例外: %s", plant_no, e)
            return None


# 全域 client（單一 session 重複使用）
_client: ThingnarioClient | None = None


def get_thingnario_client() -> ThingnarioClient:
    global _client
    if _client is None:
        _client = ThingnarioClient()
    return _client
