"""数据库方言基类 + 跨方言类型归一化"""

import re
from abc import ABC, abstractmethod

# 类型归一化规则表（顺序敏感，先匹配先返回）
# 规则：(正则模式, 目标类型)
# 注意：bool/boolean/bit 必须在 integer 之前，否则 bit 会被 integer 规则误匹配
_TYPE_RULES: list[tuple[str, str]] = [
    (r"^(bool|boolean|bit)$", "boolean"),          # boolean 优先于 integer（bit 有重叠）
    (r"(int|serial|bigserial)", "integer"),          # int, integer, bigint, smallint, tinyint, int4, int8, serial, bigserial
    (r"^NUMBER\(\d+,\s*0\)$", "integer"),           # Oracle NUMBER(10,0) / NUMBER(19,0)
    (r"(float|double|real|decimal|numeric|money)", "number"),  # 浮点 + 精确数字
    (r"^NUMBER\(\d+,\s*[1-9]\d*\)$", "number"),    # Oracle NUMBER(10,2)
    (r"^NUMBER$", "number"),                         # Oracle NUMBER（无精度）
    (r"(timestamp|datetime|date|time)", "date-time"),  # 所有日期时间类型
    (r"^(json|jsonb)$", "object"),                  # JSON 类型
    (r"(bytea|blob|varbinary|binary|image|raw)", "binary"),  # 二进制类型（含 Oracle RAW）
    (r"(varchar|text|char|clob|nvarchar|ntext|nchar|string|uuid|xml)", "string"),  # 字符串类型
]

# 预编译正则，提升性能
_COMPILED_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), target)
    for pattern, target in _TYPE_RULES
]


def normalize_type(data_type: str) -> str:
    """将各数据库方言的字段类型归一化为通用类型标识。

    支持 PostgreSQL / MySQL / SQL Server / Oracle 的常见类型。
    未知类型兜底返回 "string"。

    Args:
        data_type: 原始数据库类型字符串，如 "varchar(255)"、"NUMBER(10,0)"

    Returns:
        归一化后的类型：integer / number / string / boolean / date-time / binary / object / string
    """
    for pattern, target in _COMPILED_RULES:
        if pattern.search(data_type):
            return target
    # 未知类型兜底为 string
    return "string"


class BaseDialect(ABC):
    """数据库方言抽象基类。

    各具体方言（PostgreSQL、MySQL、SQL Server、Oracle）继承此类，
    实现 information_schema / 系统表查询的具体 SQL。

    所有方法接收已建立的 DBAPI 连接对象（conn），由调用方负责连接生命周期。
    返回值均为 dict 列表，key 名统一（与 schema_extractor 协议对齐）。
    """

    @abstractmethod
    def get_tables(self, conn) -> list[dict]:
        """获取数据库中所有用户表的元数据列表。

        Returns:
            list of dict，每项包含：
                - table_name: str
                - table_schema: str
                - table_comment: str | None
                - row_count: int | None（估算值）
        """
        ...

    @abstractmethod
    def get_columns(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """获取指定表的所有列元数据。

        Returns:
            list of dict，每项包含：
                - column_name: str
                - data_type: str（原始类型字符串）
                - normalized_type: str（由 normalize_type() 归一化后）
                - is_nullable: bool
                - column_default: str | None
                - is_primary_key: bool
                - column_comment: str | None
                - ordinal_position: int
        """
        ...

    @abstractmethod
    def get_foreign_keys(self, conn) -> list[dict]:
        """获取数据库中所有外键关系。

        Returns:
            list of dict，每项包含：
                - constraint_name: str
                - table_schema: str
                - table_name: str
                - column_name: str
                - foreign_table_schema: str
                - foreign_table_name: str
                - foreign_column_name: str
        """
        ...

    @abstractmethod
    def get_indexes(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """获取指定表的索引信息。

        Returns:
            list of dict，每项包含：
                - index_name: str
                - column_names: list[str]
                - is_unique: bool
                - is_primary: bool
        """
        ...

    @abstractmethod
    def sample_rows(self, conn, table_name: str, table_schema: str, limit: int = 20) -> list[dict]:
        """采样指定表的前 N 行数据，用于 AI 推断字段含义。

        Args:
            limit: 采样行数，默认 20

        Returns:
            list of dict，每项为一行数据（列名 → 值）
        """
        ...

    @abstractmethod
    def count_distinct(self, conn, table_name: str, table_schema: str, column_name: str) -> int:
        """统计指定列的 distinct 值数量，用于判断是否为枚举字段。

        Returns:
            distinct 值的数量
        """
        ...

    @abstractmethod
    def get_enum_values(
        self,
        conn,
        table_name: str,
        table_schema: str,
        column_name: str,
        limit: int = 50,
    ) -> list[dict]:
        """获取指定列的枚举值及其出现频次（低 cardinality 字段适用）。

        Args:
            limit: 最多返回多少个枚举值，默认 50

        Returns:
            list of dict，每项包含：
                - value: Any（原始值）
                - count: int（出现次数）
        """
        ...
