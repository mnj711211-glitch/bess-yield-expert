"""
iPVita 太陽能監控平台客戶端
用於東元旭能(大量科技) 案場
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://teco.ipvita.biz"


class iPVitaClient:
    def __init__(self, account: str, password: str):
        self._account  = account
        self._password = password
        self._session  = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._logged_in = False

    def _login(self) -> bool:
        try:
            r = self._session.post(
                f"{BASE_URL}/api/auth/login",
                json={"account": self._account, "password": self._password},
                timeout=15,
            )
            if r.status_code == 200:
                self._logged_in = True
                logger.info("iPVita 登入成功")
                return True
            logger.error("iPVita 登入失敗: %d %s", r.status_code, r.text[:200])
            return False
        except Exception as e:
            logger.error("iPVita 登入例外: %s", e)
            return False

    def _get(self, path: str) -> dict | None:
        if not self._logged_in:
            if not self._login():
                return None
        try:
            r = self._session.get(f"{BASE_URL}{path}", timeout=15)
            if r.status_code == 401:
                # session 過期，重新登入
                self._logged_in = False
                if not self._login():
                    return None
                r = self._session.get(f"{BASE_URL}{path}", timeout=15)
            if r.status_code == 200:
                return r.json()
            logger.error("iPVita GET %s 失敗: %d", path, r.status_code)
            return None
        except Exception as e:
            logger.error("iPVita GET %s 例外: %s", path, e)
            return None

    def fetch_all_sites(self) -> list[dict]:
        """回傳帳號下所有案場的即時摘要"""
        result = self._get("/api/sites")
        if not result:
            return []
        return result.get("data", [])

    def fetch_site(self, site_id: str) -> dict | None:
        """取得單一案場即時數據（by iPVita site code，如 PTW02115）"""
        for s in self.fetch_all_sites():
            if s.get("site") == site_id:
                return s
        return None

    def get_inverter_issues(self, site_id: str) -> dict | None:
        """
        比對逐台逆變器（/api/sites/{id}/realpv），挑出：
          1. 有錯誤碼的（設備錯誤）
          2. 發電量明顯低於最佳台（發電量對應日照不足）
        回傳與前端 event_detail 相容的 dict，或 None。
        """
        data = self._get(f"/api/sites/{site_id}/realpv")
        if not data:
            return None
        invs = data.get("data", []) if isinstance(data, dict) else []
        rows = []
        for d in invs:
            name = d.get("user_eqp_id") or d.get("Eqp_ID") or ""
            if not name:
                continue
            try:
                gen = float(d.get("Power_KWH") or 0)
            except (TypeError, ValueError):
                gen = 0.0
            err = str(d.get("Error_Code") or "").strip()
            rows.append((name, gen, err))
        if not rows:
            return None

        errs = [(n, e) for n, g, e in rows if e]
        max_gen = max(g for _, g, _ in rows)

        low = []
        if max_gen >= 10:  # 夜間/無日照不比對
            low = [n for n, g, _ in rows if g < 0.90 * max_gen]

        if not errs and not low:
            return None

        # 以「設備錯誤」優先，其次「發電量對應日照不足」
        if errs:
            devices = [f"{n}({e})" for n, e in errs]
            return {
                "device": "、".join(devices),
                "message": "設備錯誤",
                "category": "設備錯誤",
                "type": "逆變器",
                "count": len(devices) + len(low),
                "started": "",
            }
        return {
            "device": "、".join(low),
            "message": "發電量對應日照不足",
            "category": "發電偏低",
            "type": "逆變器",
            "count": len(low),
            "started": "",
        }


# ── 單例 ──────────────────────────────────────────────────────
_client: "iPVitaClient | None" = None

def get_ipvita_client() -> iPVitaClient:
    global _client
    if _client is None:
        _client = iPVitaClient(
            account=os.getenv("IPVITA_ACCOUNT", ""),
            password=os.getenv("IPVITA_PASSWORD", ""),
        )
    return _client


# ── 格式轉換 ──────────────────────────────────────────────────
def parse_site_data(raw: dict) -> dict:
    """
    將 iPVita /api/sites 的單筆資料轉換成 ESS Dashboard 統一格式。
    status 對照：
      "2green"   → 正常
      其他        → 告警（alert_num = 1）
    """
    status    = raw.get("status", "")
    alert_num = 0 if status == "2green" else 1

    # total_AC 單位為 W，換算成 kW
    ac_kw = round((raw.get("total_AC") or 0) / 1000, 2)

    return {
        "today_kwh":  raw.get("daily_power", 0),
        "month_kwh":  0,
        "total_kwh":  raw.get("total_kwh", 0),
        "days7":      [raw.get("daily_power", 0)] * 7,
        "efficiency": round(raw.get("daily_inverter_eff") or 0, 3),
        "ac_kw":      ac_kw,
        "radiation":  raw.get("sunshine", 0),
        "wind_speed": raw.get("wind_v"),
        "kw_pr":      round((raw.get("daily_pr") or 0) / 100, 3),
        "mod_temp":   raw.get("Module_C"),
        "amb_temp":   raw.get("EN_C"),
        "alert_num":  alert_num,
        "alert_flag": "" if alert_num == 0 else status,
        "collected":  raw.get("lm_time", ""),
        "updated":    (raw.get("lm_time") or "")[:10],
    }
