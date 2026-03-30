"""数据库连接管理 + 方言自动检测"""
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 默认端口映射
_DEFAULT_PORTS = {
    "postgresql": 5432,
    "mysql":      3306,
    "oracle":     1521,
    "mssql":      1433,
}

# 方言别名归一化（统一到标准名称）
_DIALECT_ALIASES = {
    "postgres":  "postgresql",
    "pg":        "postgresql",
    "mariadb":   "mysql",
    "sqlserver": "mssql",
}


def parse_connection_string(conn_str: str) -> dict:
    """解析连接字符串，返回规范化的连接参数字典。

    支持格式：dialect://user:pass@host:port/database

    Args:
        conn_str: 数据库连接字符串

    Returns:
        dict，键：dialect / host / port / user / password / database

    Raises:
        ValueError: 格式不合法或方言未知时
    """
    parsed = urlparse(conn_str)

    # 提取并归一化方言
    raw_dialect = parsed.scheme.lower()
    dialect = _DIALECT_ALIASES.get(raw_dialect, raw_dialect)

    host     = parsed.hostname or "localhost"
    user     = parsed.username
    password = parsed.password
    # 去掉数据库名开头的 /
    database = parsed.path.lstrip("/") if parsed.path else ""

    # 端口：URL 中有就用 URL 中的，否则取默认值
    if parsed.port:
        port = parsed.port
    else:
        port = _DEFAULT_PORTS.get(dialect)

    logger.debug(
        "解析连接字符串：dialect=%s host=%s port=%s database=%s",
        dialect, host, port, database,
    )

    return {
        "dialect":  dialect,
        "host":     host,
        "port":     port,
        "user":     user,
        "password": password,
        "database": database,
    }


def get_dialect(dialect_name: str):
    """根据方言名称懒加载并返回对应的方言实例。

    支持：postgresql / mysql / oracle / mssql

    Args:
        dialect_name: 方言名称（已归一化）

    Returns:
        BaseDialect 子类实例

    Raises:
        ValueError: 方言名称未知时
    """
    if dialect_name == "postgresql":
        from apiscout.core.db_scanner.dialect.postgresql import PostgreSQLDialect
        return PostgreSQLDialect()

    if dialect_name == "mysql":
        from apiscout.core.db_scanner.dialect.mysql import MySQLDialect
        return MySQLDialect()

    if dialect_name == "oracle":
        from apiscout.core.db_scanner.dialect.oracle import OracleDialect
        return OracleDialect()

    if dialect_name == "mssql":
        from apiscout.core.db_scanner.dialect.mssql import MSSQLDialect
        return MSSQLDialect()

    raise ValueError(f"未知的数据库方言：{dialect_name!r}，支持：postgresql / mysql / oracle / mssql")


def connect(params: dict):
    """根据连接参数创建数据库连接。

    Args:
        params: parse_connection_string() 返回的参数字典

    Returns:
        (connection, dialect_instance) 元组
        connection 为 DBAPI 2.0 连接对象，dialect_instance 为对应方言实例

    Raises:
        ValueError: 方言未知时
        ImportError: 所需驱动未安装时
        各驱动自身的连接异常
    """
    dialect_name = params["dialect"]
    dialect      = get_dialect(dialect_name)

    host     = params["host"]
    port     = params["port"]
    user     = params["user"]
    password = params["password"]
    database = params["database"]

    logger.info("正在连接数据库：%s://%s:%s/%s", dialect_name, host, port, database)

    if dialect_name == "postgresql":
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database,
        )

    elif dialect_name == "mysql":
        import mysql.connector
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )

    elif dialect_name == "oracle":
        import oracledb
        conn = oracledb.connect(
            user=user,
            password=password,
            dsn=f"{host}:{port}/{database}",
        )

    elif dialect_name == "mssql":
        import pymssql
        conn = pymssql.connect(
            server=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )

    else:
        # get_dialect() 已经会抛 ValueError，这里理论上不会走到
        raise ValueError(f"未知方言：{dialect_name!r}")

    logger.info("数据库连接成功：%s://%s:%s/%s", dialect_name, host, port, database)
    return conn, dialect
