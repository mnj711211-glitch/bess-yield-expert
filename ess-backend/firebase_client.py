"""
Firebase Admin SDK — 推送 GMS 告警到 Firestore
"""
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_db = None


def get_firestore():
    """Lazy-init Firebase Admin，回傳 Firestore client；key 不存在時回傳 None。"""
    global _db
    if _db is not None:
        return _db

    key_path = Path(__file__).parent / "firebase-key.json"
    if not key_path.exists():
        logger.warning("firebase-key.json 不存在，Firebase 功能停用")
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore as fb_firestore

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(key_path))
            firebase_admin.initialize_app(cred)

        _db = fb_firestore.client()
        logger.info("Firebase Admin 初始化成功")
        return _db
    except Exception as e:
        logger.error("Firebase Admin 初始化失敗: %s", e)
        return None


def push_gms_alert(site_name: str, alert_num: int) -> bool:
    """
    有告警時寫入 Firestore alerts 集合。
    同一案場同一天已有 GMS 告警則更新，否則新增。
    """
    db = get_firestore()
    if db is None:
        return False

    try:
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore
        today = datetime.now().strftime("%Y-%m-%d")
        now_time = datetime.now().strftime("%H:%M")
        level = "critical" if alert_num >= 3 else "warning"
        icon  = "🔴" if alert_num >= 3 else "🟡"

        existing = (
            db.collection("alerts")
            .where("site",   "==", site_name)
            .where("source", "==", "gms")
            .where("date",   "==", today)
            .get()
        )

        payload = {
            "level":     level,
            "icon":      icon,
            "site":      site_name,
            "title":     "GMS 監控告警",
            "detail":    f"目前有 {alert_num} 筆異常，請至 GMS 平台確認",
            "time":      now_time,
            "date":      today,
            "source":    "gms",
            "alert_num": alert_num,
        }

        if existing:
            for doc in existing:
                doc.reference.update(payload)
            logger.info("✓ 更新 %s GMS 告警（%d 筆）", site_name, alert_num)
        else:
            payload["created_at"] = SERVER_TIMESTAMP
            db.collection("alerts").add(payload)
            logger.info("✓ 新增 %s GMS 告警（%d 筆）", site_name, alert_num)
        return True
    except Exception as e:
        logger.error("push_gms_alert 失敗: %s", e)
        return False


def push_site_realtime(site_name: str, data: dict) -> bool:
    """
    推送案場即時監控數據到 Firestore site_realtime/{site_name}
    前端可直接從 Firestore 讀取，無需呼叫後端 API
    """
    db = get_firestore()
    if db is None:
        return False
    try:
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore
        payload = {k: v for k, v in data.items() if v is not None}
        payload["fetched_at"] = SERVER_TIMESTAMP
        db.collection("site_realtime").document(site_name).set(payload)
        return True
    except Exception as e:
        logger.error("push_site_realtime 失敗 (%s): %s", site_name, e)
        return False


def resolve_gms_alert(site_name: str) -> bool:
    """告警消失時刪除今日的 GMS 系統告警。"""
    db = get_firestore()
    if db is None:
        return False

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        docs = (
            db.collection("alerts")
            .where("site",   "==", site_name)
            .where("source", "==", "gms")
            .where("date",   "==", today)
            .get()
        )
        for doc in docs:
            doc.reference.delete()
        if docs:
            logger.info("✓ 移除 %s GMS 告警（已恢復正常）", site_name)
        return True
    except Exception as e:
        logger.error("resolve_gms_alert 失敗: %s", e)
        return False
