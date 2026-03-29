"""请求过滤 + 协议检测测试"""
from apiscout.core.capture.filter import RequestFilter, ProtocolDetector


class TestRequestFilter:

    def test_accept_api_fetch(self):
        f = RequestFilter(target_origin="https://eam.example.com")
        assert f.should_capture(
            url="https://eam.example.com/api/equipment/list",
            resource_type="fetch",
            content_type="application/json",
            status=200,
        )

    def test_reject_static_resource(self):
        f = RequestFilter(target_origin="https://eam.example.com")
        assert not f.should_capture(
            url="https://eam.example.com/static/logo.png",
            resource_type="image",
            content_type="image/png",
            status=200,
        )

    def test_reject_third_party(self):
        f = RequestFilter(target_origin="https://eam.example.com")
        assert not f.should_capture(
            url="https://cdn.example.com/lib.js",
            resource_type="script",
            content_type="application/javascript",
            status=200,
        )

    def test_reject_excluded_pattern(self):
        f = RequestFilter(
            target_origin="https://eam.example.com",
            exclude_patterns=["/logout", "/static/*"],
        )
        assert not f.should_capture(
            url="https://eam.example.com/logout",
            resource_type="document",
            content_type="text/html",
            status=302,
        )


    def test_reject_vaadin_uidl(self):
        """Vaadin UIDL 框架内部通信被过滤"""
        f = RequestFilter(target_origin="https://eam.example.com")
        assert not f.should_capture(
            url="https://eam.example.com/?v-r=uidl&v-uiId=0",
            resource_type="xhr",
            content_type="application/json",
            status=200,
        )

    def test_reject_vaadin_init(self):
        """Vaadin init 被过滤"""
        f = RequestFilter(target_origin="https://eam.example.com")
        assert not f.should_capture(
            url="https://eam.example.com/?v-r=init&location=main",
            resource_type="xhr",
            content_type="application/json",
            status=200,
        )


class TestProtocolDetector:

    def test_detect_vaadin(self):
        """检测 Vaadin UIDL 协议"""
        d = ProtocolDetector()
        assert d.classify(
            url="https://eam.example.com/?v-r=uidl&v-uiId=0",
            request_body={"csrfToken": "xxx", "rpc": []},
            response_content_type="application/json",
        ) == "vaadin"

    def test_detect_rest_json(self):
        d = ProtocolDetector()
        assert d.classify(
            url="https://eam.example.com/api/equipment/1",
            request_body=None,
            response_content_type="application/json",
        ) == "rest"

    def test_detect_graphql(self):
        d = ProtocolDetector()
        assert d.classify(
            url="https://eam.example.com/graphql",
            request_body={"query": "{ equipment { id } }"},
            response_content_type="application/json",
        ) == "graphql"

    def test_detect_soap(self):
        d = ProtocolDetector()
        assert d.classify(
            url="https://eam.example.com/ws/equipment",
            request_body="<soap:Envelope>...</soap:Envelope>",
            response_content_type="text/xml",
        ) == "soap"
