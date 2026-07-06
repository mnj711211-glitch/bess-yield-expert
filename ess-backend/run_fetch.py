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


def main() -> None:
    do_digest = len(sys.argv) > 1 and sys.argv[1] == "digest"

    logging.info("=== 開始抓取所有平台 ===")
    app.fetch_all_sites()          # 抓 5 平台 → 推 Firestore
    logging.info("=== 抓取完成 ===")

    if do_digest:
        app.send_daily_alert_digest()
        logging.info("=== 已推送 LINE 告警總覽 ===")


if __name__ == "__main__":
    main()
