"""路径参数化 + 端点归并测试"""
from apiscout.core.analyzer.router import PathParameterizer, EndpointRouter


class TestPathParameterizer:

    def test_numeric_id(self):
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/123")
        assert result == "/api/equipment/{equipmentId}"

    def test_uuid(self):
        p = PathParameterizer()
        result = p.parameterize("/api/users/550e8400-e29b-41d4-a716-446655440000")
        assert result == "/api/users/{uuid}"

    def test_snowflake_id(self):
        p = PathParameterizer()
        result = p.parameterize("/api/orders/1234567890123456789")
        assert result == "/api/orders/{snowflakeId}"

    def test_code_id(self):
        """编码型 ID: EQ202603110001"""
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/EQ202603110001")
        assert result == "/api/equipment/{code}"

    def test_nested_params(self):
        """嵌套路径参数"""
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/123/faults/456")
        assert result == "/api/equipment/{equipmentId}/faults/{faultId}"

    def test_no_param(self):
        """纯静态路径不变"""
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/list")
        assert result == "/api/equipment/list"

    def test_reserved_segments_not_parameterized(self):
        """保留词不参数化（偷师 Optic #16）"""
        p = PathParameterizer()
        result = p.parameterize("/api/v2/equipment/123")
        assert result == "/api/v2/equipment/{equipmentId}"
        result = p.parameterize("/admin/users/456")
        assert result == "/admin/users/{userId}"

    def test_date_segment_not_parameterized(self):
        """日期段不参数化（偷师 Optic #16）"""
        p = PathParameterizer()
        result = p.parameterize("/api/report/20260329")
        assert result == "/api/report/20260329"
        result = p.parameterize("/api/report/2026-03-29")
        assert result == "/api/report/2026-03-29"


class TestEndpointRouter:

    def test_insert_and_lookup(self):
        router = EndpointRouter()
        router.add("/api/equipment/123", "GET")
        router.add("/api/equipment/456", "GET")

        endpoints = router.get_endpoints()
        paths = [e["path"] for e in endpoints]
        assert "/api/equipment/{equipmentId}" in paths
        eq_endpoints = [e for e in endpoints if "equipment" in e["path"] and "{" in e["path"]]
        assert len(eq_endpoints) == 1
        assert eq_endpoints[0]["observation_count"] == 2

    def test_different_methods_same_path(self):
        router = EndpointRouter()
        router.add("/api/equipment/1", "GET")
        router.add("/api/equipment/2", "POST")

        endpoints = router.get_endpoints()
        methods = {(e["path"], e["method"]) for e in endpoints}
        assert ("/api/equipment/{equipmentId}", "GET") in methods
        assert ("/api/equipment/{equipmentId}", "POST") in methods
