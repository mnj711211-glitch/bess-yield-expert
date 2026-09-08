"""
Firebase ID Token 驗證 — 保護 /api/* 端點

前端登入 Google 後帶 Authorization: Bearer <idToken>，
這裡用 firebase_admin 驗證簽章，並檢查 email 網域是否為公司網域。

環境變數：
  AUTH_ENABLED          1=啟用驗證（預設）, 0=停用（本機除錯用）
  ALLOWED_EMAIL_DOMAIN  允許的 email 網域，多個用逗號分隔
"""
import os
import json
import logging
from pathlib import Path

from flask import request, jsonify, g

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.getenv("AUTH_ENABLED", "1") not in ("0", "false", "False", "")
ALLOWED_DOMAINS = [
    d.strip().lower().lstrip("@")
    for d in os.getenv("ALLOWED_EMAIL_DOMAIN", "greensource-tech.com").split(",")
    if d.strip()
]

# 這些路徑不需要登入：健康檢查、LINE 平台的 webhook（LINE 不會帶我們的 token）
PUBLIC_PATHS = {
    "/callback",
    "/api/health",
    "/api/line/webhook",
}

# 這些路徑只有管理者（role=admin）能呼叫：會改設定或觸發外部推播
ADMIN_PATHS = {
    "/api/refresh",
    "/api/plant-map",     # POST 會覆寫案場對照表；GET 只是讀取，見下方判斷
    "/api/line/test",
    "/api/discover",
}

# ── 授權名單（allowed_users.json）────────────────────────
# 名單存在且不為空 → 只有名單上的 email 能存取；名單檔不存在 → 退回只檢查網域。
_USERS_FILE = Path(__file__).parent / "allowed_users.json"
_users_cache: dict = {}
_users_mtime: float = -1.0


def allowed_users() -> dict:
    """回傳 {email: {name, team}}，檔案有變動時自動重讀。"""
    global _users_cache, _users_mtime
    try:
        mtime = _USERS_FILE.stat().st_mtime
    except OSError:
        if _users_mtime != -2:
            logger.warning("allowed_users.json 不存在，改為只檢查 email 網域")
            _users_mtime = -2
        return {}

    if mtime != _users_mtime:
        try:
            data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
            _users_cache = {
                u["email"].strip().lower(): u
                for u in data.get("users", [])
                if u.get("email")
            }
            _users_mtime = mtime
            logger.info("授權名單已載入：%d 人", len(_users_cache))
        except Exception as e:
            logger.error("allowed_users.json 解析失敗，沿用前一份名單: %s", e)
    return _users_cache


def _init_admin() -> bool:
    """確保 firebase_admin 已初始化（沿用 firebase_client 的 key）。"""
    try:
        import firebase_admin
        if not firebase_admin._apps:
            from firebase_client import get_firestore
            get_firestore()          # 內部會 initialize_app
        return bool(firebase_admin._apps)
    except Exception as e:
        logger.error("firebase_admin 初始化失敗，無法驗證 token: %s", e)
        return False


def verify_token(id_token: str):
    """驗證 token，回傳 (claims, None) 或 (None, 錯誤訊息)。"""
    if not _init_admin():
        return None, "伺服器驗證服務尚未就緒"

    from firebase_admin import auth as fb_auth
    try:
        claims = fb_auth.verify_id_token(id_token)
    except fb_auth.ExpiredIdTokenError:
        return None, "登入已逾期，請重新登入"
    except fb_auth.RevokedIdTokenError:
        return None, "登入憑證已被撤銷，請重新登入"
    except Exception as e:
        logger.warning("token 驗證失敗: %s", e)
        return None, "登入憑證無效"

    email = (claims.get("email") or "").lower()
    if not email:
        return None, "此帳號沒有 email，無法授權"
    if not claims.get("email_verified"):
        return None, "email 尚未驗證"

    domain = email.rsplit("@", 1)[-1]
    if ALLOWED_DOMAINS and domain not in ALLOWED_DOMAINS:
        logger.info("拒絕非公司網域登入: %s", email)
        return None, f"僅限 @{ALLOWED_DOMAINS[0]} 帳號使用"

    users = allowed_users()
    if users and email not in users:
        logger.info("拒絕未授權帳號: %s", email)
        return None, "此帳號未被授權使用戰情板，請聯絡管理員"

    claims["_profile"] = users.get(email, {})
    return claims, None


def require_auth():
    """
    before_request 用：未通過驗證時回傳 Response，通過則回傳 None。
    通過後 g.user = {uid, email, name}。
    """
    if not AUTH_ENABLED:
        return None
    if request.method == "OPTIONS":          # CORS preflight
        return None

    path = request.path.rstrip("/") or "/"
    if path in PUBLIC_PATHS or not path.startswith("/api/"):
        return None

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return jsonify({"ok": False, "error": "需要登入", "code": "auth_required"}), 401

    claims, err = verify_token(header[7:].strip())
    if err:
        return jsonify({"ok": False, "error": err, "code": "auth_failed"}), 401

    profile = claims.get("_profile") or {}
    g.user = {
        "uid":   claims.get("uid") or claims.get("sub"),
        "email": claims.get("email"),
        "name":  profile.get("name") or claims.get("name", ""),
        "team":  profile.get("team", ""),
        "role":  profile.get("role", "staff"),
    }

    # 管理端點：GET /api/plant-map 只是讀取，放行；其餘一律限管理者
    is_admin_path = path in ADMIN_PATHS and not (
        path == "/api/plant-map" and request.method == "GET"
    )
    if is_admin_path and g.user["role"] != "admin":
        logger.info("非管理者嘗試存取 %s: %s", path, g.user["email"])
        return jsonify({
            "ok": False, "error": "此操作僅限管理者", "code": "admin_only"
        }), 403

    return None
