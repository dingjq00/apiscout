"""数据库方言层 — 导出四种方言供 schema_extractor 使用"""

from .base import BaseDialect, normalize_type
from .postgresql import PostgreSQLDialect
from .mysql import MySQLDialect
from .oracle import OracleDialect
from .mssql import MSSQLDialect

__all__ = [
    "BaseDialect",
    "normalize_type",
    "PostgreSQLDialect",
    "MySQLDialect",
    "OracleDialect",
    "MSSQLDialect",
]
