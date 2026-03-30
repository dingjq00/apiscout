"""关系推断 — 从字段命名模式推断表间关系"""
import re
import logging
from apiscout.core.db_scanner.models import InferredRelation

logger = logging.getLogger(__name__)

# 审计字段集合（created_by / updated_by 等常见审计列）
_AUDIT_COLUMNS = {
    "created_by", "updated_by", "modified_by", "deleted_by",
    "create_by", "update_by", "creator", "updater",
}

# 用户表候选名（按优先级排列）
_USER_TABLE_CANDIDATES = [
    "sys_user", "user", "users", "sys_users",
    "t_user", "t_users", "admin_user", "uc_user", "auth_user",
]

# 框架前缀（用于 _find_table_by_prefix 补全查找）
_TABLE_PREFIXES = ["t_", "sys_", "tb_"]


def _find_user_table(all_tables: set[str]) -> str | None:
    """在已知候选列表中寻找用户表"""
    for candidate in _USER_TABLE_CANDIDATES:
        if candidate in all_tables:
            return candidate
    return None


def _find_table_by_prefix(prefix: str, all_tables: set[str]) -> str | None:
    """
    根据前缀字符串在表名集合中寻找匹配表。
    尝试顺序：直接匹配 → t_前缀 → sys_前缀 → tb_前缀
    """
    # 直接匹配
    if prefix in all_tables:
        return prefix
    # 加框架前缀后匹配
    for fp in _TABLE_PREFIXES:
        candidate = fp + prefix
        if candidate in all_tables:
            return candidate
    return None


def infer_relations(
    source_table: str,
    column_names: list[str],
    table_map: dict,
) -> list[InferredRelation]:
    """
    从字段命名模式推断表间关系。

    参数：
        source_table  — 当前表名
        column_names  — 当前表的所有列名列表
        table_map     — {"table_name": {"columns": set[str]}} 全库表结构

    返回：
        推断出的 InferredRelation 列表（可能为空）
    """
    all_tables: set[str] = set(table_map.keys())
    source_columns: set[str] = set(table_map.get(source_table, {}).get("columns", set()))
    results: list[InferredRelation] = []

    for col in column_names:
        # ----------------------------------------------------------------
        # 规则 1：parent_id → 自引用（置信度 0.85）
        # ----------------------------------------------------------------
        if col == "parent_id":
            if "id" in source_columns:
                rel = InferredRelation(
                    source_table=source_table,
                    source_column=col,
                    target_table=source_table,
                    target_column="id",
                    confidence=0.85,
                    evidence=f"parent_id → {source_table}.id（自引用树形结构）",
                )
                results.append(rel)
                logger.debug("推断自引用关系：%s.%s → %s.id", source_table, col, source_table)
            continue  # parent_id 优先处理，不再走后续规则

        # ----------------------------------------------------------------
        # 规则 2：审计字段 → 用户表（置信度 0.8）
        # ----------------------------------------------------------------
        if col in _AUDIT_COLUMNS:
            user_table = _find_user_table(all_tables)
            if user_table is not None:
                user_columns = table_map[user_table].get("columns", set())
                if "id" in user_columns:
                    rel = InferredRelation(
                        source_table=source_table,
                        source_column=col,
                        target_table=user_table,
                        target_column="id",
                        confidence=0.8,
                        evidence=f"审计字段 {col} → {user_table}.id（操作人外键）",
                    )
                    results.append(rel)
                    logger.debug("推断审计关系：%s.%s → %s.id", source_table, col, user_table)
            continue  # 审计字段不再走 _id/_code 规则

        # ----------------------------------------------------------------
        # 规则 3：xxx_id → xxx.id（置信度 0.9）
        # ----------------------------------------------------------------
        id_match = re.match(r"^(.+)_id$", col)
        if id_match:
            prefix = id_match.group(1)
            target = _find_table_by_prefix(prefix, all_tables)
            if target is not None and target != source_table:
                target_columns = table_map[target].get("columns", set())
                if "id" in target_columns:
                    rel = InferredRelation(
                        source_table=source_table,
                        source_column=col,
                        target_table=target,
                        target_column="id",
                        confidence=0.9,
                        evidence=f"命名规范推断：{col} → {target}.id",
                    )
                    results.append(rel)
                    logger.debug("推断 _id 关系：%s.%s → %s.id", source_table, col, target)
            continue

        # ----------------------------------------------------------------
        # 规则 4：xxx_code → xxx.code（置信度 0.7）
        # ----------------------------------------------------------------
        code_match = re.match(r"^(.+)_code$", col)
        if code_match:
            prefix = code_match.group(1)
            target = _find_table_by_prefix(prefix, all_tables)
            if target is not None and target != source_table:
                target_columns = table_map[target].get("columns", set())
                if "code" in target_columns:
                    rel = InferredRelation(
                        source_table=source_table,
                        source_column=col,
                        target_table=target,
                        target_column="code",
                        confidence=0.7,
                        evidence=f"命名规范推断：{col} → {target}.code",
                    )
                    results.append(rel)
                    logger.debug("推断 _code 关系：%s.%s → %s.code", source_table, col, target)

    return results
