"""
LINE Messaging API 推播模組
發送告警通知到指定群組
"""

import os, logging
import requests

logger = logging.getLogger(__name__)

LINE_API = "https://api.line.me/v2/bot/message/push"

def _token() -> str:
    return os.getenv("LINE_TOKEN", "")

def _group_id() -> str:
    return os.getenv("LINE_GROUP_ID", "")


def send_alert(site: str, level: str, detail: str, alert_num: int) -> bool:
    """單一案場告警（保留相容性，內部呼叫 send_alert_summary）"""
    return send_alert_summary([{
        "site": site, "level": level, "detail": detail, "alert_num": alert_num
    }])


def send_alert_summary(alerts: list) -> bool:
    """
    發送多案場合併告警到 LINE 群組，所有告警在同一則訊息。
    alerts: [{"site": str, "level": str, "alert_num": int, "detail": str}, ...]
    """
    token    = _token()
    group_id = _group_id()

    if not token or not group_id:
        logger.warning("LINE_TOKEN 或 LINE_GROUP_ID 未設定，跳過 LINE 推播")
        return False

    if not alerts:
        return False

    critical = [a for a in alerts if a["level"] == "critical"]
    warning  = [a for a in alerts if a["level"] != "critical"]

    header_icon = "🔴" if critical else "🟡"
    header_type = "嚴重告警" if critical else "警告通知"
    total = len(alerts)

    lines = [
        f"{header_icon} ESS 戰情版｜{header_type}（{total} 個案場）",
        f"━━━━━━━━━━━━━━━",
    ]

    for a in critical + warning:
        icon = "🔴" if a["level"] == "critical" else "🟡"
        lines.append(f"{icon} {a['site']}｜{a['alert_num']} 筆異常")

    lines += [
        f"━━━━━━━━━━━━━━━",
        f"請登入 ESS 戰情版確認處理。",
    ]

    text = "\n".join(lines)
    payload = {
        "to": group_id,
        "messages": [{"type": "text", "text": text}]
    }

    try:
        r = requests.post(
            LINE_API,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json=payload,
            timeout=8,
        )
        if r.status_code == 200:
            logger.info("LINE 推播成功: %d 個案場告警", total)
            return True
        else:
            logger.error("LINE 推播失敗: %d %s", r.status_code, r.text)
            return False
    except Exception as e:
        logger.error("LINE 推播例外: %s", e)
        return False


def send_resolved(site: str) -> bool:
    """發送告警解除通知"""
    token    = _token()
    group_id = _group_id()

    if not token or not group_id:
        return False

    text = (
        f"✅ ESS 戰情版｜告警解除\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📍 案場：{site}\n"
        f"狀態已恢復正常。"
    )

    payload = {
        "to": group_id,
        "messages": [{"type": "text", "text": text}]
    }

    try:
        r = requests.post(
            LINE_API,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json=payload,
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False


def send_test() -> dict:
    """測試推播，回傳結果 dict"""
    token    = _token()
    group_id = _group_id()

    if not token:
        return {"ok": False, "error": "LINE_TOKEN 未設定"}
    if not group_id:
        return {"ok": False, "error": "LINE_GROUP_ID 未設定"}

    text = (
        "🔔 ESS 戰情版｜連線測試\n"
        "━━━━━━━━━━━━━━━\n"
        "LINE 通知已成功啟用！\n"
        "告警發生時將自動推播至此群組。"
    )

    payload = {
        "to": group_id,
        "messages": [{"type": "text", "text": text}]
    }

    try:
        r = requests.post(
            LINE_API,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json=payload,
            timeout=8,
        )
        if r.status_code == 200:
            return {"ok": True, "message": "測試訊息已發送"}
        else:
            return {"ok": False, "error": f"LINE API 回傳 {r.status_code}: {r.text}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
