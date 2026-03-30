"""枚举探测 + 随机采样"""
import logging
from copy import copy

from apiscout.core.db_scanner.models import ColumnInfo

logger = logging.getLogger(__name__)

# cardinality 低于此阈值时判定为枚举候选
ENUM_CARDINALITY_THRESHOLD = 50

# 跳过枚举探测的归一化类型（二进制/JSON 对象无意义）
_SKIP_ENUM_TYPES = {"binary", "object"}


def scan_table_samples(
    conn,
    dialect,
    table_name: str,
    table_schema: str,
    columns: list[ColumnInfo],
    enum_threshold: int = ENUM_CARDINALITY_THRESHOLD,
    sample_limit: int = 20,
) -> tuple[list[ColumnInfo], list[dict]]:
    """枚举探测 + 随机行采样。

    对每个非 PK、非二进制列执行 count_distinct 查询：
    - 0 < cardinality < enum_threshold → 拉取枚举值列表并写入 ColumnInfo 副本
    - 其余列保持原样

    Args:
        conn: 已建立的 DBAPI 连接对象
        dialect: BaseDialect 实例，提供 SQL 方言实现
        table_name: 目标表名
        table_schema: 目标 schema 名
        columns: 原始 ColumnInfo 列表（不会被修改）
        enum_threshold: cardinality 上限，低于此值才视为枚举
        sample_limit: 采样行数上限

    Returns:
        (updated_columns, sample_rows)
        - updated_columns: 新列表，枚举列的 enum_values 已填充，其余不变
        - sample_rows: 采样行列表（list of dict）
    """
    updated_columns: list[ColumnInfo] = []

    for col in columns:
        # PK 列跳过（PK 天然高 cardinality，查了也没用）
        if col.is_primary_key:
            updated_columns.append(col)
            continue

        # binary / object 类型跳过（采枚举没有意义）
        if col.normalized_type in _SKIP_ENUM_TYPES:
            updated_columns.append(col)
            continue

        try:
            cardinality = dialect.count_distinct(conn, table_name, table_schema, col.name)

            if 0 < cardinality < enum_threshold:
                # 低 cardinality → 认为是枚举，拉取所有离散值
                enum_vals = dialect.get_enum_values(conn, table_name, table_schema, col.name)
                # 不修改原始对象，创建副本后设置 enum_values
                new_col = copy(col)
                new_col.enum_values = enum_vals
                updated_columns.append(new_col)
                logger.debug(
                    "枚举探测命中：%s.%s cardinality=%d，值数=%d",
                    table_name, col.name, cardinality, len(enum_vals),
                )
            else:
                # 高 cardinality 或空表，保持原样
                updated_columns.append(col)

        except Exception:
            # 单列失败不影响整体，记录后继续
            logger.debug("枚举探测失败，跳过列：%s.%s", table_name, col.name, exc_info=True)
            updated_columns.append(col)

    # 采样若干行，供 AI 增强阶段推断字段含义
    sample_rows = dialect.sample_rows(conn, table_name, table_schema, limit=sample_limit)

    return updated_columns, sample_rows
