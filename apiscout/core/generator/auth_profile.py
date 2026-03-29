"""认证档案生成 — 偷师 Nango 的 YAML 配置 + TWO_STEP 模式"""
from pathlib import Path

import yaml

from apiscout.core.capture.store import CaptureRecord


# 登录请求 body 关键词
LOGIN_BODY_KEYWORDS = {"username", "password", "account", "user", "passwd", "login_name"}
# Token 响应字段关键词（去下划线后匹配）
TOKEN_FIELD_KEYWORDS = {"token", "accesstoken", "jwt", "idtoken"}
# Refresh 请求 body 关键词
REFRESH_BODY_KEYWORDS = {"refresh_token", "refreshtoken", "refresh"}


def find_login_endpoint(records: list[CaptureRecord]) -> dict | None:
    """从捕获记录中识别登录和 refresh 端点"""
    login_info = None
    refresh_info = None

    for record in records:
        if record.method != "POST" or not isinstance(record.request_body, dict):
            continue

        body_keys_lower = {k.lower() for k in record.request_body.keys()}

        # 检测登录端点
        if body_keys_lower & LOGIN_BODY_KEYWORDS:
            token_location = _find_token_in_response(record.response_body)
            if token_location:
                login_info = {
                    "endpoint": f"{record.method} {record.path}",
                    "token_location": token_location,
                    "request_fields": list(record.request_body.keys()),
                }

        # 检测 refresh 端点
        if body_keys_lower & REFRESH_BODY_KEYWORDS:
            refresh_info = {
                "refresh_endpoint": f"{record.method} {record.path}",
            }

    if login_info and refresh_info:
        login_info.update(refresh_info)
    elif refresh_info and not login_info:
        # 只有 refresh 没有 login，也返回
        login_info = refresh_info

    return login_info


def _find_token_in_response(body, prefix="response") -> str | None:
    """递归查找响应 body 中的 token 字段"""
    if not isinstance(body, dict):
        return None
    for key, value in body.items():
        current_path = f"{prefix}.{key}"
        # 去下划线后小写匹配
        if key.lower().replace("_", "") in TOKEN_FIELD_KEYWORDS:
            return current_path
        if isinstance(value, dict):
            result = _find_token_in_response(value, current_path)
            if result:
                return result
    return None


# insight68 接入建议映射
INSIGHT68_ADAPTERS = {
    "bearer_jwt": {"auth_adapter": "jwt_bearer", "required_from_customer": ["服务账号用户名", "密码"]},
    "bearer": {"auth_adapter": "bearer_token", "required_from_customer": ["Token"]},
    "basic": {"auth_adapter": "basic", "required_from_customer": ["用户名", "密码"]},
    "api_key": {"auth_adapter": "api_key", "required_from_customer": ["API Key"]},
    "cookie": {"auth_adapter": "session", "required_from_customer": ["服务账号用户名", "密码"]},
    "custom_header": {"auth_adapter": "custom_header", "required_from_customer": ["对应 vendor 配置字段"]},
    "none": {"auth_adapter": "none", "required_from_customer": []},
}


def generate_auth_profile(
    auth_info: dict,
    login_info: dict | None = None,
) -> dict:
    """生成认证档案"""
    profile = {
        "auth": dict(auth_info),
    }

    # 登录流信息
    if login_info:
        profile["auth"]["discovery"] = login_info

    # insight68 接入建议（偷师 Nango 的 provider config 思路）
    auth_type = auth_info.get("type", "none")
    hint = dict(INSIGHT68_ADAPTERS.get(auth_type, INSIGHT68_ADAPTERS["none"]))

    # 特殊处理：非标 vendor（偷师 Nango TWO_STEP 模式）
    if auth_type == "custom_header" and "vendor" in auth_info:
        hint["vendor"] = auth_info["vendor"]

    profile["insight68_config_hint"] = hint

    return profile


def write_auth_profile(
    auth_info: dict,
    output_path: str,
    login_info: dict | None = None,
):
    """生成并写入认证档案 YAML"""
    profile = generate_auth_profile(auth_info, login_info=login_info)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
