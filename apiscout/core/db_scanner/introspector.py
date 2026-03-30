"""Schema 扫描编排 — 组合 connector + dialect + sampler + relations"""
import fnmatch
import logging
from datetime import datetime, timezone

from apiscout.core.db_scanner.models import (
    ColumnInfo,
    IndexInfo,
    ExplicitRelation,
    TableInfo,
    SchemaReport,
)
from apiscout.core.db_scanner.connector import parse_connection_string, connect
from apiscout.core.db_scanner.sampler import scan_table_samples
from apiscout.core.db_scanner.relations import infer_relations

logger = logging.getLogger(__name__)


def scan_database(
    conn_str: str | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
    dialect: str | None = None,
    exclude_patterns: list[str] | None = None,
) -> SchemaReport:
    """扫描数据库 Schema，返回完整的 SchemaReport。

    连接参数支持两种方式：
    - 传入 conn_str（优先）：如 "postgresql://user:pass@host:5432/eam"
    - 传入关键字参数：host / port / user / password / database / dialect

    Args:
        conn_str:  数据库连接字符串（优先）
        host:      数据库主机
        port:      端口号
        user:      用户名
        password:  密码
        database:  数据库名
        dialect:   方言：postgresql / mysql / oracle / mssql

    Returns:
        SchemaReport 实例，含所有表、列、索引、关系信息

    Raises:
        ValueError: 参数不足或方言未知
        各驱动的连接异常
    """
    # -----------------------------------------------------------------------
    # Step 1：解析连接参数
    # -----------------------------------------------------------------------
    if conn_str:
        params = parse_connection_string(conn_str)
    else:
        # 用关键字参数构造 params
        if not dialect:
            raise ValueError("未传入 conn_str 时必须指定 dialect 参数")
        params = {
            "dialect":  dialect,
            "host":     host or "localhost",
            "port":     port,
            "user":     user,
            "password": password,
            "database": database or "",
        }
        logger.debug("使用关键字参数构造连接：%s", params)

    # -----------------------------------------------------------------------
    # Step 2：建立连接
    # -----------------------------------------------------------------------
    conn, dialect_instance = connect(params)

    try:
        # -------------------------------------------------------------------
        # Step 3：获取所有表
        # -------------------------------------------------------------------
        raw_tables = dialect_instance.get_tables(conn)
        # 排除匹配黑名单的表（fnmatch 通配符，如 act_*, qrtz_*）
        if exclude_patterns:
            before = len(raw_tables)
            raw_tables = [
                t for t in raw_tables
                if not any(fnmatch.fnmatch(t["name"], pat) for pat in exclude_patterns)
            ]
            excluded = before - len(raw_tables)
            if excluded:
                logger.info("排除 %d 张表（匹配 --exclude 规则）", excluded)
        logger.info("发现 %d 张表", len(raw_tables))

        # -------------------------------------------------------------------
        # Step 4：获取所有外键，构建 ExplicitRelation 列表
        # -------------------------------------------------------------------
        raw_fks = dialect_instance.get_foreign_keys(conn)
        explicit_relations: list[ExplicitRelation] = []
        # 同时记录外键已覆盖的 (table, column) 集合，供后续推断关系排除
        fk_covered: set[tuple[str, str]] = set()

        for fk in raw_fks:
            rel = ExplicitRelation(
                source_table=fk["source_table"],
                source_column=fk["source_column"],
                target_table=fk["target_table"],
                target_column=fk["target_column"],
                constraint_name=fk["constraint_name"],
            )
            explicit_relations.append(rel)
            fk_covered.add((fk["source_table"], fk["source_column"]))

        logger.info("发现 %d 个外键约束", len(explicit_relations))

        # -------------------------------------------------------------------
        # Step 5：逐表处理
        # -------------------------------------------------------------------
        tables: list[TableInfo] = []
        # table_map 供 infer_relations 使用：{table_name: {"columns": set[str]}}
        table_map: dict[str, dict] = {}

        for raw in raw_tables:
            tbl_name   = raw["name"]
            tbl_schema = raw["schema"]

            # ---- 5a. 列元数据 ----
            raw_cols = dialect_instance.get_columns(conn, tbl_name, tbl_schema)
            columns: list[ColumnInfo] = []
            for rc in raw_cols:
                col = ColumnInfo(
                    name=rc["name"],
                    data_type=rc["data_type"],
                    normalized_type=rc["normalized_type"],
                    nullable=rc["nullable"],
                    default=rc.get("default"),
                    comment=rc.get("comment"),
                    max_length=rc.get("max_length"),
                    numeric_precision=rc.get("numeric_precision"),
                    is_primary_key=rc["is_primary_key"],
                    enum_values=None,
                )
                columns.append(col)

            # ---- 5b. 索引元数据 ----
            raw_indexes = dialect_instance.get_indexes(conn, tbl_name, tbl_schema)
            indexes: list[IndexInfo] = []
            for ri in raw_indexes:
                idx = IndexInfo(
                    name=ri["name"],
                    columns=ri["columns"],
                    is_unique=ri["is_unique"],
                    is_primary=ri["is_primary"],
                )
                indexes.append(idx)

            # ---- 5c. 枚举探测 + 采样 ----
            updated_columns, sample_rows = scan_table_samples(
                conn, dialect_instance, tbl_name, tbl_schema, columns,
                row_count=raw.get("row_count"),
            )

            # ---- 5d. 构建 TableInfo ----
            table_info = TableInfo(
                name=tbl_name,
                schema=tbl_schema,
                comment=raw.get("comment"),
                row_count=raw.get("row_count"),
                columns=updated_columns,
                indexes=indexes,
                sample_rows=sample_rows,
            )
            tables.append(table_info)

            # ---- 5e. 累积 table_map ----
            table_map[tbl_name] = {
                "columns": {c.name for c in updated_columns},
            }

            logger.debug(
                "表 %s.%s 处理完毕：%d 列，%d 索引，%d 样本行",
                tbl_schema, tbl_name, len(updated_columns), len(indexes), len(sample_rows),
            )

        # -------------------------------------------------------------------
        # Step 6：推断隐式关系（排除已有外键覆盖的列）
        # -------------------------------------------------------------------
        from apiscout.core.db_scanner.models import InferredRelation
        all_inferred: list[InferredRelation] = []

        for table_info in tables:
            # 只对尚未被外键覆盖的列推断关系
            candidate_cols = [
                col.name
                for col in table_info.columns
                if (table_info.name, col.name) not in fk_covered
            ]

            if candidate_cols:
                inferred = infer_relations(
                    source_table=table_info.name,
                    column_names=candidate_cols,
                    table_map=table_map,
                )
                all_inferred.extend(inferred)

        logger.info("推断隐式关系 %d 条", len(all_inferred))

        # -------------------------------------------------------------------
        # Step 7：构建并返回 SchemaReport
        # -------------------------------------------------------------------
        report = SchemaReport(
            dialect=params["dialect"],
            database=params["database"],
            scanned_at=datetime.now(timezone.utc).isoformat(),
            tables=tables,
            explicit_relations=explicit_relations,
            inferred_relations=all_inferred,
        )

        logger.info(
            "扫描完成：%d 表，%d 列，%d 外键，%d 推断关系",
            report.total_tables,
            report.total_columns,
            report.total_foreign_keys,
            report.total_inferred_relations,
        )
        return report

    finally:
        # -------------------------------------------------------------------
        # Step 8：确保连接被关闭（即使中途异常）
        # -------------------------------------------------------------------
        conn.close()
        logger.debug("数据库连接已关闭")
