"""Schema 推断引擎测试"""
from apiscout.core.analyzer.schema_engine import SchemaEngine


def test_basic_merge():
    """多次观察合并"""
    engine = SchemaEngine()
    engine.add_observation({"id": 1, "name": "设备A", "status": 1})
    engine.add_observation({"id": 2, "name": "设备B", "status": 2, "memo": "备注"})
    schema = engine.get_schema()

    assert schema["type"] == "object"
    assert "id" in schema.get("required", [])
    assert "name" in schema.get("required", [])
    assert "memo" not in schema.get("required", [])


def test_nullable_detection():
    """None 值产生 nullable"""
    engine = SchemaEngine()
    engine.add_observation({"status": 1})
    engine.add_observation({"status": None})
    schema = engine.get_schema()

    status_type = schema["properties"]["status"]["type"]
    assert "null" in str(status_type) or "anyOf" in str(schema["properties"]["status"])


def test_format_enhancement():
    """string format 检测"""
    engine = SchemaEngine()
    engine.add_observation({
        "created_at": "2026-03-29T14:30:00Z",
        "email": "user@example.com",
        "device_id": "550e8400-e29b-41d4-a716-446655440000",
    })
    schema = engine.get_schema()
    enhanced = engine.enhance_schema(schema)

    props = enhanced["properties"]
    assert props["created_at"].get("format") == "date-time"
    assert props["email"].get("format") == "email"
    assert props["device_id"].get("format") == "uuid"


def test_enum_detection():
    """重复出现的少量值 → enum"""
    engine = SchemaEngine()
    for status in [1, 2, 1, 3, 2, 1, 2, 1, 3, 1]:
        engine.add_observation({"status": status})
    schema = engine.get_schema()
    enhanced = engine.enhance_schema(schema)

    assert "enum" in enhanced["properties"]["status"]
    assert set(enhanced["properties"]["status"]["enum"]) == {1, 2, 3}
