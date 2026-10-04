"""Worker-auth passthrough guard (PART 5).

Asserts the precise AuthMiddleware contract:
- Exactly POST /api/worker-auth/login is public (never "Sign-in required.").
- Every route starting with "/api/worker/" (trailing slash) plus
  POST /api/worker-auth/change-password skips the Supabase check and
  returns 401 from the worker Bearer check without a valid worker token.
- No looser "/api/worker" prefix match; AUTH_DISABLED block untouched.

Run:  py -3 -m unittest backend.tests.test_worker_auth_passthrough -v
Stdlib unittest only (+ fastapi TestClient, already a backend dep).
"""
import unittest
import uuid

DUMMY_TASK = "00000000-0000-0000-0000-000000000000"


def _concrete(path: str) -> str:
    return path.replace("{task_id}", DUMMY_TASK)


class TestWorkerAuthPassthrough(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.main import app
        from fastapi.testclient import TestClient
        cls.app = app
        cls.client = TestClient(app, raise_server_exceptions=False)
        # Enumerate from the mounted routers directly: newer FastAPI nests
        # included routers (app.routes only shows _IncludedRouter stubs),
        # so walk worker.router (prefix /api/worker) + the change-password
        # route (prefix /api/worker-auth). This stays exhaustive: any new
        # route added to worker.py is picked up automatically.
        from backend.api.endpoints import worker as worker_mod
        from backend.api.endpoints import worker_auth as worker_auth_mod
        routes = []
        for r in worker_mod.router.routes:
            sub = getattr(r, "path", "") or ""
            methods = sorted(getattr(r, "methods", set()) or set())
            routes.append(("/api/worker" + sub, methods))
        for r in worker_auth_mod.router.routes:
            sub = getattr(r, "path", "") or ""
            methods = sorted(getattr(r, "methods", set()) or set())
            if sub.rstrip("/") == "/change-password":
                routes.append(("/api/worker-auth" + sub, methods))
        cls.protected = sorted(routes)

    def test_discovers_all_worker_routes(self):
        # 9 /worker/* routes + change-password = 10 protected entries.
        self.assertGreaterEqual(len(self.protected), 10,
                                f"expected >=10 protected routes, got {self.protected}")
        paths = [p for p, _ in self.protected]
        for want in ("/api/worker/me", "/api/worker/tasks", "/api/worker/alerts",
                     "/api/worker/availability", "/api/worker/incidents",
                     "/api/worker-auth/change-password"):
            self.assertIn(want, paths, f"missing {want} in {paths}")

    def _request(self, method, path, **kw):
        c = self.__class__.client
        if method == "GET":
            return c.get(path, **kw)
        if method == "POST":
            return c.post(path, **kw)
        if method == "PUT":
            return c.put(path, **kw)
        if method == "PATCH":
            return c.patch(path, **kw)
        if method == "DELETE":
            return c.delete(path, **kw)
        self.fail(f"unsupported method {method}")

    def _body_for(self, method, path):
        if path.endswith("/change-password"):
            return {"current_password": "wrong-current", "new_password": "new-password-123"}
        if path.endswith("/availability"):
            return {"availability": "AVAILABLE"}
        if path.endswith("/incidents"):
            return {"severity": "LOW", "description": "passthrough probe"}
        if path.endswith("/status"):
            return {"status": "IN_PROGRESS"}
        if path.endswith("/progress"):
            return {"progress": 0.5}
        if path.endswith("/output"):
            return {"quantity": 1}
        return {}

    def test_protected_routes_401_without_worker_token(self):
        for path, methods in self.protected:
            for method in methods:
                if method == "OPTIONS":
                    continue
                url = _concrete(path)
                kw = {}
                if method in ("POST", "PUT", "PATCH"):
                    kw["json"] = self._body_for(method, path)
                with self.subTest(route=f"{method} {url} no-header"):
                    r = self._request(method, url, **kw)
                    self.assertEqual(r.status_code, 401, f"{method} {url}: {r.status_code} {r.text[:200]}")
                    self.assertNotEqual(r.json().get("detail"), "Sign-in required.",
                                        f"{method} {url} hit Supabase middleware instead of worker check")
                with self.subTest(route=f"{method} {url} bogus-bearer"):
                    r = self._request(method, url, headers={"Authorization": "Bearer bogus-token"},
                                      **kw)
                    self.assertEqual(r.status_code, 401, f"{method} {url}: {r.status_code} {r.text[:200]}")
                    self.assertNotEqual(r.json().get("detail"), "Sign-in required.",
                                        f"{method} {url} hit Supabase middleware instead of worker check")

    def test_login_is_public(self):
        c = self.__class__.client
        r = c.post("/api/worker-auth/login",
                   json={"identifier": "no-such-user-xyz", "password": "wrong"})
        # Reaches the endpoint (401 invalid creds, or 500 if migrations not applied).
        # Must NEVER be the Supabase "Sign-in required." gate.
        self.assertIn(r.status_code, (401, 500), f"login: {r.status_code} {r.text[:200]}")
        if r.status_code == 401:
            self.assertEqual(r.json().get("detail"), "Invalid username or password.")
        else:
            self.assertNotEqual(r.json().get("detail"), "Sign-in required.")

    def test_middleware_uses_precise_prefixes(self):
        with open("backend/core/auth_middleware.py", encoding="utf-8") as f:
            src = f.read()
        self.assertIn('path.startswith("/api/worker/")', src)
        self.assertIn('"/api/worker-auth/login"', src)
        self.assertIn('"/api/worker-auth/change-password"', src)
        # No looser "/api/worker" literal (closing quote right after
        # "worker", without the trailing slash) anywhere in the file.
        self.assertEqual(src.count('"/api/worker"'), 0,
                         "looser /api/worker prefix detected")
        # AUTH_DISABLED behavior untouched.
        self.assertIn("if settings.AUTH_DISABLED:", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
