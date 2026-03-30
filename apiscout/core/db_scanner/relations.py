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


def _find_table_by_prefix(
    prefix: str,
    all_tables: set[str],
    source_table: str = "",
) -> str | None:
    """
    根据前缀字符串在表名集合中寻找匹配表。

    搜索优先级：
    1. 直接匹配：category → category
    2. 框架前缀：category → t_category / sys_category / tb_category
    3. 同模块后缀匹配：source=eam_equipment, prefix=category → eam_equipment_category / eam_category
    4. 全局后缀匹配：category → *_category（按名称最短优先）
    """
    # 1. 直接匹配
    if prefix in all_tables:
        return prefix

    # 2. 加框架前缀
    for fp in _TABLE_PREFIXES:
        candidate = fp + prefix
        if candidate in all_tables:
            return candidate

    # 3. 同模块后缀匹配（source_table 的前缀 + prefix）
    if source_table and "_" in source_table:
        # eam_equipment → 尝试 eam_equipment_category, eam_category
        parts = source_table.split("_")
        # 尝试完整表名_前缀（eam_equipment_category）
        candidate = f"{source_table}_{prefix}"
        if candidate in all_tables:
            return candidate
        # 尝试模块前缀（eam_category）
        module = parts[0]
        candidate = f"{module}_{prefix}"
        if candidate in all_tables:
            return candidate

    # 4. 全局后缀匹配 — 找所有以 _prefix 结尾的表，取最短的（最精确）
    suffix = f"_{prefix}"
    candidates = [t for t in all_tables if t.endswith(suffix)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # 多个候选 — 优先同模块前缀，其次最短
        if source_table and "_" in source_table:
            module = source_table.split("_")[0]
            same_module = [t for t in candidates if t.startswith(module + "_")]
            if len(same_module) == 1:
                return same_module[0]
        return min(candidates, key=len)

    # system_ 前缀特殊处理（若依系统表）
    candidate = f"system_{prefix}"
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
            target = _find_table_by_prefix(prefix, all_tables, source_table)
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
            target = _find_table_by_prefix(prefix, all_tables, source_table)
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
