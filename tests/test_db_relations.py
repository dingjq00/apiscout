"""关系推断测试 — 四条命名规则"""
import pytest

from apiscout.core.db_scanner.models import InferredRelation
from apiscout.core.db_scanner.relations import infer_relations


def _make_table_map():
    return {
        "device": {"columns": {"id", "name", "device_type_id", "parent_id", "created_by"}},
        "device_type": {"columns": {"id", "name", "code"}},
        "work_order": {"columns": {"id", "device_id", "status", "created_by", "updated_by"}},
        "sys_user": {"columns": {"id", "username", "name"}},
    }


# ---------- 规则 3：xxx_id → xxx.id ----------

def test_xxx_id_pattern():
    """work_order.device_id 应推断为 device.id，置信度 0.9"""
    table_map = _make_table_map()
    relations = infer_relations(
        source_table="work_order",
        column_names=["device_id"],
        table_map=table_map,
    )
    assert len(relations) == 1
    rel = relations[0]
    assert isinstance(rel, InferredRelation)
    assert rel.source_table == "work_order"
    assert rel.source_column == "device_id"
    assert rel.target_table == "device"
    assert rel.target_column == "id"
    assert rel.confidence == 0.9


# ---------- 规则 1：parent_id → 自引用 ----------

def test_parent_id_self_reference():
    """device.parent_id 应推断为 device.id 自引用，置信度 0.85"""
    table_map = _make_table_map()
    relations = infer_relations(
        source_table="device",
        column_names=["parent_id"],
        table_map=table_map,
    )
    assert len(relations) == 1
    rel = relations[0]
    assert rel.source_table == "device"
    assert rel.source_column == "parent_id"
    assert rel.target_table == "device"
    assert rel.target_column == "id"
    assert rel.confidence == 0.85


# ---------- 规则 2：审计字段 → 用户表 ----------

def test_created_by_user():
    """work_order.created_by + updated_by 都应推断为 sys_user.id，共 2 条关系"""
    table_map = _make_table_map()
    relations = infer_relations(
        source_table="work_order",
        column_names=["created_by", "updated_by"],
        table_map=table_map,
    )
    assert len(relations) == 2
    for rel in relations:
        assert rel.target_table == "sys_user"
        assert rel.target_column == "id"
        assert rel.confidence == 0.8
    cols = {r.source_column for r in relations}
    assert cols == {"created_by", "updated_by"}


def test_created_by_no_user_table():
    """没有用户表时，created_by 不产生关系"""
    table_map = {
        "order": {"columns": {"id", "created_by"}},
        # 故意不放任何用户表
    }
    relations = infer_relations(
        source_table="order",
        column_names=["created_by"],
        table_map=table_map,
    )
    assert relations == []


# ---------- 规则 4（以及规则 3 综合）：device_type_id ----------

def test_xxx_code_pattern():
    """device.device_type_id 应推断为 device_type.id（规则 3）"""
    table_map = _make_table_map()
    relations = infer_relations(
        source_table="device",
        column_names=["device_type_id"],
        table_map=table_map,
    )
    assert len(relations) == 1
    rel = relations[0]
    assert rel.source_column == "device_type_id"
    assert rel.target_table == "device_type"
    assert rel.target_column == "id"
    assert rel.confidence == 0.9


def test_xxx_code_suffix():
    """xxx_code → xxx.code 规则（置信度 0.7）"""
    table_map = {
        "work_order": {"columns": {"id", "device_code"}},
        "device": {"columns": {"id", "code", "name"}},
    }
    relations = infer_relations(
        source_table="work_order",
        column_names=["device_code"],
        table_map=table_map,
    )
    assert len(relations) == 1
    rel = relations[0]
    assert rel.source_column == "device_code"
    assert rel.target_table == "device"
    assert rel.target_column == "code"
    assert rel.confidence == 0.7


# ---------- 无误报 ----------

def test_no_false_positives():
    """name、status 等普通字段不应产生任何关系"""
    table_map = _make_table_map()
    relations = infer_relations(
        source_table="device",
        column_names=["name"],
        table_map=table_map,
    )
    assert relations == []

    relations = infer_relations(
        source_table="work_order",
        column_names=["status"],
        table_map=table_map,
    )
    assert relations == []


def test_nonexistent_table_no_match():
    """work_order.category_id 找不到 category 表，不产生关系"""
    table_map = _make_table_map()
    relations = infer_relations(
        source_table="work_order",
        column_names=["category_id"],
        table_map=table_map,
    )
    assert relations == []


# ---------- 框架前缀匹配 ----------

def test_t_prefix_table_match():
    """order.device_id 能匹配 t_device 表（t_ 前缀补全）"""
    table_map = {
        "order": {"columns": {"id", "device_id"}},
        "t_device": {"columns": {"id", "name"}},
    }
    relations = infer_relations(
        source_table="order",
        column_names=["device_id"],
        table_map=table_map,
    )
    assert len(relations) == 1
    assert relations[0].target_table == "t_device"


def test_sys_prefix_table_match():
    """order.dept_id 能匹配 sys_dept 表（sys_ 前缀补全）"""
    table_map = {
        "order": {"columns": {"id", "dept_id"}},
        "sys_dept": {"columns": {"id", "name"}},
    }
    relations = infer_relations(
        source_table="order",
        column_names=["dept_id"],
        table_map=table_map,
    )
    assert len(relations) == 1
    assert relations[0].target_table == "sys_dept"


# ---------- 自引用不跨表 ----------

def test_xxx_id_does_not_self_reference():
    """如果 device.device_id 存在且 prefix==source_table，不产生关系（排除自引用场景）"""
    table_map = {
        "device": {"columns": {"id", "device_id"}},
    }
    relations = infer_relations(
        source_table="device",
        column_names=["device_id"],
        table_map=table_map,
    )
    # device_id → device，但 target == source，应被过滤
    assert relations == []


# ---------- 综合多列 ----------

def test_multiple_columns_combined():
    """device 表所有列一起推断，应得到 parent_id(自引用) + device_type_id + created_by 三条"""
    table_map = _make_table_map()
    relations = infer_relations(
        source_table="device",
        column_names=list(table_map["device"]["columns"]),
        table_map=table_map,
    )
    # 预期：parent_id→device.id, device_type_id→device_type.id, created_by→sys_user.id
    assert len(relations) == 3
    by_col = {r.source_column: r for r in relations}
    assert "parent_id" in by_col
    assert by_col["parent_id"].target_table == "device"
    assert "device_type_id" in by_col
    assert by_col["device_type_id"].target_table == "device_type"
    assert "created_by" in by_col
    assert by_col["created_by"].target_table == "sys_user"
