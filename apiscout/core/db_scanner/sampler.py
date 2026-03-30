"""枚举探测 + 随机采样

枚举检测策略（参考 ydata-profiling 双门槛机制）：
- 通用规则过滤（类型、字段名模式）
- 双门槛：cardinality 绝对值 + cardinality/行数比例
- 值级检查：排除 JSON、超长文本
- 置信度分级：high / medium / low，不追求 100% 准确，交给人/AI 最终判断
"""
import re
import logging
from copy import copy

from apiscout.core.db_scanner.models import ColumnInfo

logger = logging.getLogger(__name__)

# cardinality 低于此阈值时判定为枚举候选
ENUM_CARDINALITY_THRESHOLD = 30

# cardinality / row_count 比例超过此值则不是枚举（只是数据少）
ENUM_RATIO_THRESHOLD = 0.3

# 跳过枚举探测的归一化类型
_SKIP_ENUM_TYPES = {"binary", "object", "date-time"}

# 跳过枚举探测的字段名模式（只保留通用的，不放业务特定词）
_SKIP_ENUM_NAME_PATTERNS = [
    r".*_id$",          # 外键字段
    r"^id$",            # 主键
    r".*_ids$",         # 多值 ID 列表
    r".*_url$",         # URL
    r".*_urls$",        # URL 列表
    r".*_path$",        # 路径
    r".*_time$",        # 时间字段
    r".*_date$",        # 日期字段
    r".*_at$",          # 时间戳（created_at）
    r".*_json$",        # JSON 字段
    r".*_content$",     # 内容字段
    r"^creator$",       # 创建人（审计字段，值是用户ID/名）
    r"^updater$",       # 更新人
]
_SKIP_ENUM_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SKIP_ENUM_NAME_PATTERNS]


def _classify_enum_confidence(
    col: ColumnInfo,
    cardinality: int,
    row_count: int | None,
) -> str:
    """判断枚举候选的置信度

    Returns: "high" / "medium" / "low"
    """
    # 高置信度：boolean 类型，或 smallint/int 且 cardinality ≤ 5
    if col.normalized_type == "boolean":
        return "high"
    if col.normalized_type == "integer" and cardinality <= 5:
        return "high"

    # 中置信度：cardinality ≤ 10 且比例低
    if cardinality <= 10:
        if row_count and row_count > 0 and cardinality / row_count < 0.1:
            return "medium"
        return "medium"

    # 低置信度：其余通过门槛的
    return "low"


def scan_table_samples(
    conn,
    dialect,
    table_name: str,
    table_schema: str,
    columns: list[ColumnInfo],
    row_count: int | None = None,
    enum_threshold: int = ENUM_CARDINALITY_THRESHOLD,
    sample_limit: int = 20,
) -> tuple[list[ColumnInfo], list[dict]]:
    """枚举探测 + 随机行采样。

    枚举探测采用多层过滤 + 置信度分级，不追求 100% 准确：
    - 类型过滤：date-time、text、binary 跳过
    - 字段名过滤：*_id、*_url、*_time 等通用模式跳过
    - 双门槛：cardinality > 1 且 < 阈值，且比例 < 30%
    - 值级过滤：JSON 内容、超长文本跳过
    - 通过以上全部的标记为枚举候选，附带置信度

    Args:
        conn: 已建立的 DBAPI 连接对象
        dialect: BaseDialect 实例
        table_name: 目标表名
        table_schema: 目标 schema 名
        columns: 原始 ColumnInfo 列表（不会被修改）
        row_count: 表的估算行数
        enum_threshold: cardinality 上限
        sample_limit: 采样行数上限

    Returns:
        (updated_columns, sample_rows)
    """
    updated_columns: list[ColumnInfo] = []

    for col in columns:
        # PK 列跳过
        if col.is_primary_key:
            updated_columns.append(col)
            continue

        # 类型跳过：binary / object / date-time
        if col.normalized_type in _SKIP_ENUM_TYPES:
            updated_columns.append(col)
            continue

        # text 数据库类型跳过（长文本）
        if col.data_type.lower() in ("text", "clob", "ntext", "mediumtext", "longtext"):
            updated_columns.append(col)
            continue

        # 字段名模式跳过（通用规则）
        if any(p.match(col.name) for p in _SKIP_ENUM_COMPILED):
            updated_columns.append(col)
            continue

        try:
            cardinality = dialect.count_distinct(conn, table_name, table_schema, col.name)

            if 1 < cardinality < enum_threshold:
                # 比例检查：distinct/rows > 30% → 只是数据少，不是枚举
                if row_count and row_count > 0 and cardinality / row_count > ENUM_RATIO_THRESHOLD:
                    updated_columns.append(col)
                    continue

                # 拉取离散值
                enum_vals = dialect.get_enum_values(conn, table_name, table_schema, col.name)

                # 值级过滤：JSON 内容或超长文本
                avg_len = sum(len(str(v.get("value", ""))) for v in enum_vals) / max(len(enum_vals), 1)
                has_json = any("{" in str(v.get("value", "")) for v in enum_vals)
                if avg_len > 50 or has_json:
                    updated_columns.append(col)
                    continue

                # 通过所有门槛 → 标记为枚举候选，附带置信度
                confidence = _classify_enum_confidence(col, cardinality, row_count)
                new_col = copy(col)
                new_col.enum_values = [
                    {**v, "confidence": confidence} for v in enum_vals
                ]
                updated_columns.append(new_col)
                logger.debug(
                    "枚举候选：%s.%s cardinality=%d 置信度=%s",
                    table_name, col.name, cardinality, confidence,
                )
            else:
                updated_columns.append(col)

        except Exception:
            logger.debug("枚举探测失败，跳过列：%s.%s", table_name, col.name, exc_info=True)
            updated_columns.append(col)

    # 随机采样
    sample_rows = dialect.sample_rows(conn, table_name, table_schema, limit=sample_limit)

    return updated_columns, sample_rows
