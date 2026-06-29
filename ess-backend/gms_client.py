"""
GMS (gms.auo.com) 資料擷取模組
- 登入取得 session
- 查詢可用案場清單
- 下載指定案場的日發電量 CSV
"""

import os, io, time, logging
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL   = os.getenv("GMS_URL", "https://gms.auo.com/MvcWebPortal")
USERNAME   = os.getenv("GMS_USERNAME", "")
PASSWORD   = os.getenv("GMS_PASSWORD", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9",
}


import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GMSClient:
    def __init__(self):
        self.session   = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = False  # GMS 使用非標準內部憑證
        self.logged_in = False

    # ── 登入 ──────────────────────────────────────
    def login(self) -> bool:
        try:
            # Step 1: GET 登入頁取得 cookie（必要）
            self.session.get(f"https://gms.auo.com/MvcWebPortal/", timeout=15)

            # Step 2: POST JSON 登入（正確端點為 /Login/Login3）
            payload = {"Act": USERNAME, "Psw": PASSWORD, "RememberMe": True}
            r2 = self.session.post(
                "https://gms.auo.com/MvcWebPortal/Login/Login3",
                json=payload,
                headers={"Content-Type": "application/json",
                         "X-Requested-With": "XMLHttpRequest"},
                timeout=15,
            )
            data = r2.json() if r2.headers.get("Content-Type","").startswith("application/json") else {}
            logger.info("GMS 登入回應: %s", r2.status_code)

            # 成功回應: JSON array [{"Act":"...","Authority":"..."}]
            if r2.status_code == 200 and isinstance(data, list) and len(data) > 0 and "Act" in data[0]:
                self.logged_in = True
                logger.info("GMS 登入成功 (Act=%s...)", data[0]["Act"][:10])
                return True

            logger.error("GMS 登入失敗: %s", data)
            return False
        except Exception as e:
            logger.error("GMS 登入例外: %s", e)
            return False

    def ensure_logged_in(self):
        if not self.logged_in:
            if not self.login():
                raise RuntimeError("無法登入 GMS，請確認帳密")

    # ── 取得案場清單 ──────────────────────────────
    def get_plant_list(self) -> list[dict]:
        """回傳 GMS 上所有案場，含即時發電功率"""
        self.ensure_logged_in()
        r = self.session.get("https://gms.auo.com/MvcWebPortal/api/GetPlants", timeout=20)
        r.raise_for_status()
        plants = r.json()
        # 標準化欄位名稱
        result = []
        for p in plants:
            result.append({
                "plantNo":   p.get("PlantNo", ""),
                "name":      p.get("PlantName", ""),
                "capacity":  p.get("Capacity", 0),
                "ac_kw":        p.get("ac_kw", 0),
                "radiation":    p.get("radiation", 0),
                "wind_speed":   p.get("wind_speed"),
                "kw_pr":        p.get("KW_PR", 0),
                "mod_temp":     p.get("module_temperature"),
                "amb_temp":     p.get("ambient_temperature"),
                "alert_num":    p.get("Alert_Num"),
                "alert_flag":   p.get("Alert_flag", ""),
                "city":         p.get("City", ""),
                "state":        p.get("State", ""),
                "on_grid_date": p.get("OnGridDate", ""),
                "collected":    p.get("collection_time", ""),
            })
        logger.info("取得案場清單: %d 筆", len(result))
        return result

    # ── 取得案場即時數據 ──────────────────────────
    def fetch_realtime(self, plant_no: str) -> dict | None:
        """
        從 GetPlants 取得指定案場的即時數據。
        回傳: {today_kwh, month_kwh, total_kwh, days7, efficiency, ac_kw}
        """
        self.ensure_logged_in()
        plants = self.get_plant_list()
        for p in plants:
            if p["plantNo"] == plant_no:
                ac_kw = p.get("ac_kw") or 0
                # 估算今日發電量（即時功率 × 平均有效日照 6h，粗估值）
                today_kwh = round(ac_kw * 6, 1)
                return {
                    "today_kwh":  today_kwh,
                    "month_kwh":  0,
                    "total_kwh":  0,
                    "days7":      [today_kwh] * 7,
                    "efficiency": round(ac_kw / p["capacity"], 3) if p["capacity"] else 0,
                    "ac_kw":        ac_kw,
                    "radiation":    p.get("radiation", 0),
                    "wind_speed":   p.get("wind_speed"),
                    "kw_pr":        p.get("kw_pr", 0),
                    "mod_temp":     p.get("mod_temp"),
                    "amb_temp":     p.get("amb_temp"),
                    "alert_num":    p.get("alert_num"),
                    "alert_flag":   p.get("alert_flag", ""),
                    "collected":    p.get("collected", ""),
                }
        return None

    # ── 取得告警明細 ──────────────────────────────
    def fetch_device_alerts(self, plant_no: str) -> list[dict]:
        """
        嘗試從 GMS 取得指定案場的告警明細。
        多個候選 endpoint 逐一試，回傳第一個有資料的結果。
        若 GMS 無此 API 則回傳 []。
        """
        self.ensure_logged_in()

        candidate_paths = [
            f"/api/GetAlerts?plantNo={plant_no}",
            f"/api/GetAlertList?plantNo={plant_no}",
            f"/DeviceInfo/GetAlerts?plantNo={plant_no}",
            f"/DeviceInfo/GetDeviceAlerts?plantNo={plant_no}",
            f"/api/Alert/List?plantNo={plant_no}",
            f"/Alert/GetList?plantNo={plant_no}",
        ]

        for path in candidate_paths:
            try:
                r = self.session.get(
                    f"https://gms.auo.com/MvcWebPortal{path}", timeout=15
                )
                if r.status_code != 200:
                    continue
                ct = r.headers.get("Content-Type", "")
                if "json" not in ct:
                    continue
                data = r.json()
                # 直接是 list
                if isinstance(data, list) and len(data) > 0:
                    logger.info("GMS 告警明細 %s: %d 筆 (%s)", plant_no, len(data), path)
                    return data
                # dict 包裝
                if isinstance(data, dict):
                    for key in ("data", "alerts", "list", "items", "result", "Alerts"):
                        inner = data.get(key)
                        if isinstance(inner, list) and len(inner) > 0:
                            logger.info("GMS 告警明細 %s: %d 筆 (key=%s)", plant_no, len(inner), key)
                            return inner
            except Exception as e:
                logger.debug("GMS 告警端點失敗 %s: %s", path, e)

        logger.warning("GMS 告警明細: 未找到有效端點 (plant_no=%s)", plant_no)
        return []

    # ── 下載日發電量 CSV ──────────────────────────
    def fetch_daily_csv(
        self,
        plant_no: str,
        from_date: str | None = None,
        to_date:   str | None = None,
        interval:  str = "日",
        datasource: str = "system",
    ) -> pd.DataFrame | None:
        """
        下載指定案場的發電量報表並回傳 DataFrame。
        from_date / to_date 格式: "2026/06/01"
        """
        self.ensure_logged_in()

        today = date.today()
        to_date   = to_date   or today.strftime("%Y/%m/%d")
        from_date = from_date or (today - timedelta(days=30)).strftime("%Y/%m/%d")

        export_paths = [
            "/DataExport/Export",
            "/Report/Export",
            "/DataExport/DownloadCsv",
            "/api/export/csv",
        ]
        params = {
            "plantNO":    plant_no,
            "interval":   interval,
            "from":       from_date,
            "to":         to_date,
            "datasource": datasource,
        }

        for path in export_paths:
            try:
                r = self.session.get(BASE_URL + path, params=params, timeout=30)
                ct = r.headers.get("Content-Type", "")
                if r.status_code == 200 and ("csv" in ct or "text" in ct or "octet" in ct):
                    df = pd.read_csv(io.StringIO(r.text))
                    logger.info("成功下載 CSV: %s (%d rows)", plant_no, len(df))
                    return df
            except Exception as e:
                logger.debug("嘗試 %s 失敗: %s", path, e)

        logger.warning("無法下載 CSV (plantNO=%s)，請用 DevTools 確認正確 URL", plant_no)
        return None

    # ── 解析 DataFrame → 標準格式 ─────────────────
    @staticmethod
    def parse_generation(df: pd.DataFrame) -> dict:
        """
        將不同格式的 CSV DataFrame 轉成標準字典:
        {
          "today_kwh": float,
          "month_kwh": float,
          "total_kwh": float,
          "days7":     [float, ...],   # 最近7天每日
          "efficiency": float,         # kWh/kWp (today)
        }
        """
        result = {
            "today_kwh": 0,
            "month_kwh": 0,
            "total_kwh": 0,
            "days7": [],
            "efficiency": 0,
            "raw_columns": list(df.columns),
        }
        # 嘗試常見欄位名稱（中英文混合）
        kwh_cols = [c for c in df.columns if any(k in c.lower() for k in
                    ["kwh","發電","energy","generation","yield","power"])]
        date_cols = [c for c in df.columns if any(k in c.lower() for k in
                    ["date","日期","time","時間"])]

        if kwh_cols and date_cols:
            df2 = df[[date_cols[0], kwh_cols[0]]].copy()
            df2.columns = ["date", "kwh"]
            df2["kwh"] = pd.to_numeric(df2["kwh"], errors="coerce").fillna(0)
            df2 = df2.sort_values("date")
            result["today_kwh"] = float(df2["kwh"].iloc[-1]) if len(df2) > 0 else 0
            result["month_kwh"] = float(df2["kwh"].sum())
            result["days7"]     = df2["kwh"].tail(7).tolist()
        return result


# 全域 client（單一 session 重複使用）
_client: GMSClient | None = None

def get_client() -> GMSClient:
    global _client
    if _client is None:
        _client = GMSClient()
    return _client
