import os
import sys
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from backend.middleware.xss_protection import strip_dangerous_xss_tags

class TestXSSHardening(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)

    def test_strip_dangerous_xss_tags_vectors(self):
        # 1. Script tag vector
        self.assertNotIn("<script>", strip_dangerous_xss_tags("<script>alert('xss')</script>"))
        # 2. Iframe javascript vector (OWASP Report Section 3.5 & 5.2)
        self.assertNotIn("javascript:", strip_dangerous_xss_tags('<iframe src="javascript:alert(`xss`)">'))
        # 3. Image onerror vector (OWASP Report Section 5.5)
        self.assertNotIn("onerror=", strip_dangerous_xss_tags('<img src=x onerror=alert(1)>'))
        # 4. SVG onload vector (OWASP Report Section 3.6)
        self.assertNotIn("<svg", strip_dangerous_xss_tags('<svg onload=alert(1)>'))
        # 5. Case-insensitive bypass attempt (OWASP Report Section 3.6)
        self.assertNotIn("javascript:", strip_dangerous_xss_tags('<a href="JaVaScRiPt:alert(1)">link</a>'))

    def test_http_security_headers_response(self):
        res = self.client.get("/api/v1/health")
        self.assertEqual(res.status_code, 200)
        self.assertIn("X-XSS-Protection", res.headers)
        self.assertEqual(res.headers["X-XSS-Protection"], "1; mode=block")
        self.assertIn("X-Content-Type-Options", res.headers)
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("X-Frame-Options", res.headers)
        self.assertEqual(res.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("Content-Security-Policy", res.headers)
        csp = res.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)

    def test_header_injection_xss_sanitization(self):
        headers = {
            "True-Client-IP": "127.0.0.1<script>alert('header_xss')</script>",
            "User-Agent": "<img src=x onerror=alert('agent')>"
        }
        res = self.client.get("/api/v1/health", headers=headers)
        self.assertEqual(res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
