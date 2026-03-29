"""端点去重 + 数据聚合 — 将 CaptureRecord 流汇总为端点列表"""
from collections import defaultdict
from urllib.parse import urlparse, parse_qs

from apiscout.core.capture.store import CaptureRecord
from apiscout.core.analyzer.router import EndpointRouter
from apiscout.core.analyzer.schema_engine import SchemaEngine
from apiscout.core.analyzer.auth_detector import AuthDetector


class EndpointAggregator:
    """将原始捕获记录聚合为去重的端点 + schema + query params"""

    def __init__(self):
        self._router = EndpointRouter()
        self._request_schemas: dict[tuple, SchemaEngine] = defaultdict(SchemaEngine)
        self._response_schemas: dict[tuple, SchemaEngine] = defaultdict(SchemaEngine)
        self._query_params: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._status_codes: dict[tuple, set] = defaultdict(set)
        self._all_headers: list[dict] = []
        self._js_endpoints: set[str] = set()

    def add(self, record: CaptureRecord):
        """添加一条捕获记录"""
        if record.protocol != "rest":
            return

        path = record.path
        method = record.method
        self._router.add(path, method)

        parameterized = self._router.lookup(path, method)
        key = (parameterized, method.upper())

        if isinstance(record.response_body, dict):
            self._response_schemas[key].add_observation(record.response_body)

        if isinstance(record.request_body, dict):
            self._request_schemas[key].add_observation(record.request_body)

        # 收集 query 参数
        parsed = urlparse(record.url)
        for param_name, param_values in parse_qs(parsed.query).items():
            self._query_params[key][param_name].extend(param_values)

        self._status_codes[key].add(record.status)

        if record.request_headers:
            self._all_headers.append(record.request_headers)

    def add_js_endpoint(self, path: str):
        """记录 JS 分析发现但未触发的端点"""
        self._js_endpoints.add(path)

    def get_results(self) -> list[dict]:
        """获取聚合后的端点列表"""
        router_endpoints = self._router.get_endpoints()
        results = []

        triggered_paths = set()
        for ep in router_endpoints:
            key = (ep["path"], ep["method"])
            resp_engine = self._response_schemas.get(key)
            req_engine = self._request_schemas.get(key)

            resp_schema = {}
            if resp_engine:
                raw = resp_engine.get_schema()
                resp_schema = resp_engine.enhance_schema(raw)

            req_schema = {}
            if req_engine:
                raw = req_engine.get_schema()
                req_schema = req_engine.enhance_schema(raw)

            # 推断 query 参数 schema
            query_params_info = []
            for qp_name, qp_values in sorted(self._query_params.get(key, {}).items()):
                all_int = all(v.isdigit() for v in qp_values if v)
                schema = {"type": "integer"} if all_int else {"type": "string"}
                unique = set(qp_values)
                if 1 < len(unique) <= 10 and len(qp_values) > len(unique):
                    schema["enum"] = sorted(unique, key=lambda x: (not x.isdigit(), x))
                query_params_info.append({
                    "name": qp_name,
                    "in": "query",
                    "schema": schema,
                    "required": True,
                })

            results.append({
                "path": ep["path"],
                "method": ep["method"],
                "observation_count": ep["observation_count"],
                "status_codes": sorted(self._status_codes.get(key, set())),
                "response_schema": resp_schema,
                "request_schema": req_schema,
                "query_params": query_params_info,
                "status": "confirmed",
            })
            triggered_paths.add(ep["path"])

        # JS 发现但未触发的端点
        for js_path in self._js_endpoints:
            if js_path not in triggered_paths:
                results.append({
                    "path": js_path,
                    "method": "UNKNOWN",
                    "observation_count": 0,
                    "status_codes": [],
                    "response_schema": {},
                    "request_schema": {},
                    "query_params": [],
                    "status": "uncertain",
                })

        return results

    def get_auth_profile(self) -> dict:
        """获取认证档案"""
        detector = AuthDetector()
        return detector.detect(self._all_headers)
