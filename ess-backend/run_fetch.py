"""
GitHub Actions 專用：執行一次資料抓取並推送 Firestore。
- 無參數：抓 5 個平台 → 推 Firestore（含白天斷線偵測）
- 參數 'digest'：抓取後另外推送 LINE 告警總覽（09:00 / 16:00 用）

不啟動 Flask 伺服器（app.run 受 __main__ 保護），適合排程一次性執行。
"""
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

from dotenv import load_dotenv
load_dotenv()

import app  # noqa: E402  匯入即載入 PLANT_MAP 等設定與函式


def write_line_diag() -> None:
    """把雲端實際用到的 LINE 設定狀態寫入 Firestore _diag/line 供除錯。"""
    try:
        import os, requests
        from firebase_client import get_firestore
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP
        tok = os.getenv("LINE_TOKEN", "")
        gid = os.getenv("LINE_GROUP_ID", "")
        H = {"Authorization": f"Bearer {tok}"}
        info = requests.get("https://api.line.me/v2/bot/info", headers=H, timeout=8)
        grp_status = "NO_GID"
        if gid:
            g = requests.get(f"https://api.line.me/v2/bot/group/{gid}/summary", headers=H, timeout=8)
            grp_status = g.status_code
        db = get_firestore()
        if db:
            db.collection("_diag").document("line").set({
                "token_len":    len(tok),
                "token_valid":  info.status_code,      # 200 = token 正確
                "group_tail":   gid[-6:] if gid else "EMPTY",
                "group_status": grp_status,            # 200 = bot 在該群組
                "ts":           SERVER_TIMESTAMP,
            })
    except Exception as e:
        logging.warning("write_line_diag 失敗: %s", e)


def main() -> None:
    do_digest = len(sys.argv) > 1 and sys.argv[1] == "digest"

    logging.info("=== 開始抓取所有平台 ===")
    app.fetch_all_sites()          # 抓 5 平台 → 推 Firestore
    logging.info("=== 抓取完成 ===")

    write_line_diag()              # 寫 LINE 設定診斷到 Firestore

    if do_digest:
        app.send_daily_alert_digest()
        logging.info("=== 已推送 LINE 告警總覽 ===")


if __name__ == "__main__":
    main()
