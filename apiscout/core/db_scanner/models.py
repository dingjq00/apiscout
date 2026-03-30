"""数据库 Schema 扫描数据模型"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ColumnInfo:
    """单列元数据"""
    name: str
    data_type: str                  # 原始数据库类型，如 INT、VARCHAR(255)
    normalized_type: str            # 统一类型：integer/string/number/boolean/date-time
    nullable: bool
    default: str | None
    comment: str | None
    max_length: int | None
    numeric_precision: int | None
    is_primary_key: bool
    enum_values: list[dict] | None  # [{"value": "ACTIVE", "count": 500}]，None 表示未采样

    @property
    def is_enum_candidate(self) -> bool:
        """是否可能是枚举列（有离散值样本）"""
        return self.enum_values is not None


@dataclass
class IndexInfo:
    """索引元数据"""
    name: str
    columns: list[str]
    is_unique: bool
    is_primary: bool


@dataclass
class ExplicitRelation:
    """通过外键约束明确声明的关系"""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    constraint_name: str            # 数据库约束名


@dataclass
class InferredRelation:
    """通过命名规范或值域推断的隐式关系"""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    confidence: float               # 置信度 0.0 ~ 1.0
    evidence: str                   # 推断依据描述，便于人工审核


@dataclass
class TableInfo:
    """单表元数据"""
    name: str
    schema: str                     # 数据库 schema（如 public、dbo）
    comment: str | None
    row_count: int | None           # 估算行数，None 表示无法获取
    columns: list[ColumnInfo]
    indexes: list[IndexInfo]
    sample_rows: list[dict]         # 少量采样行，用于 AI 增强


@dataclass
class SchemaReport:
    """完整的 Schema 扫描报告，覆盖一个数据库的所有表和关系"""
    dialect: str                    # 方言：postgresql / mysql / mssql / oracle / sqlite
    database: str                   # 数据库名
    scanned_at: str                 # UTC ISO-8601 时间戳
    tables: list[TableInfo]
    explicit_relations: list[ExplicitRelation]
    inferred_relations: list[InferredRelation]

    @property
    def total_tables(self) -> int:
        """表总数"""
        return len(self.tables)

    @property
    def total_columns(self) -> int:
        """所有表的列总数"""
        return sum(len(t.columns) for t in self.tables)

    @property
    def total_foreign_keys(self) -> int:
        """显式外键数"""
        return len(self.explicit_relations)

    @property
    def total_inferred_relations(self) -> int:
        """推断关系数"""
        return len(self.inferred_relations)

    @property
    def enum_candidates(self) -> list[ColumnInfo]:
        """所有可能是枚举的列（跨表汇总）"""
        return [
            col
            for table in self.tables
            for col in table.columns
            if col.is_enum_candidate
        ]
