import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from noteboard.memos_client import (ApiError, AuthError, MemosClient,
                                    NetworkError, NotFoundError, format_time,
                                    parse_time)


def _memo(i, state="NORMAL"):
    return {"name": f"memos/{i}", "state": state, "content": f"c{i}",
            "createTime": "2026-01-02T03:04:05Z",
            "updateTime": "2026-01-02T03:04:05.123456789Z", "pinned": True,
            "visibility": "PUBLIC", "attachments": [{"name": "x"}]}


class Handler(BaseHTTPRequestHandler):
    log: list = []
    status = 200

    def log_message(self, *a):
        pass

    def _reply(self, payload, status=None):
        body = json.dumps(payload).encode()
        self.send_response(status or self.status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        Handler.log.append((self.command, u.path, q, body,
                            self.headers.get("Authorization")))
        if self.status != 200:
            return self._reply({"message": "nope"})
        if u.path == "/api/v1/auth/me":
            return self._reply({"user": {"name": "users/7"}})
        if u.path == "/api/v1/memos" and self.command == "GET":
            # 3 NORMAL memos over 2 pages, 1 ARCHIVED.
            if q["state"] == "ARCHIVED":
                return self._reply({"memos": [_memo(9, "ARCHIVED")]})
            if q.get("pageToken") == "p2":
                return self._reply({"memos": [_memo(3)]})
            return self._reply({"memos": [_memo(1), _memo(2)], "nextPageToken": "p2"})
        return self._reply(_memo(5))

    do_GET = do_POST = do_PATCH = do_DELETE = _handle


class ClientTest(unittest.TestCase):
    def setUp(self):
        Handler.log, Handler.status = [], 200
        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/"
        self.c = MemosClient(self.url, "tok", timeout=3, page_size=2)

    def test_list_all_paginates_both_states_filtered_by_creator(self):
        memos = self.c.list_all()
        self.assertEqual([m.id for m in memos], ["1", "2", "3", "9"])
        self.assertEqual(memos[3].state, "ARCHIVED")
        self.assertEqual(memos[0].update_time, parse_time("2026-01-02T03:04:05.123Z"))
        lists = [e for e in Handler.log if e[1] == "/api/v1/memos"]
        self.assertEqual(len(lists), 3)
        self.assertTrue(all(e[2]["filter"] == 'creator == "users/7"' for e in lists))
        self.assertTrue(all(e[4] == "Bearer tok" for e in Handler.log))

    def test_update_sends_mask_and_no_attachments(self):
        self.c.update("5", {"content": "x", "pinned": False})
        _, path, q, body, _ = Handler.log[-1]
        self.assertEqual((path, q["updateMask"]),
                         ("/api/v1/memos/5", "content,pinned,update_time"))
        self.assertNotIn("updateTime", body)
        self.assertNotIn("attachments", body)

    def test_create_passes_memo_id_and_create_time(self):
        self.c.create({"content": "x", "create_time": 1_000}, memo_id="abc")
        _, _, q, body, _ = Handler.log[-1]
        self.assertEqual(q["memoId"], "abc")
        self.assertEqual(body["createTime"], "1970-01-01T00:00:01.000Z")

    def test_errors_are_typed(self):
        for status, exc in ((401, AuthError), (404, NotFoundError), (400, ApiError)):
            Handler.status = status
            with self.assertRaises(exc) as cm:
                self.c.get("1")
            self.assertIn("nope", str(cm.exception))
        Handler.status = 400
        with self.assertRaises(ApiError) as cm:
            self.c.get("1")
        self.assertEqual(cm.exception.status, 400)

    def test_unreachable_is_network_error(self):
        self.httpd.shutdown()
        with self.assertRaises(NetworkError):
            self.c.get("1")

    def test_time_round_trip(self):
        for ms in (0, 1, 1_767_323_045_123):
            self.assertEqual(parse_time(format_time(ms)), ms)


if __name__ == "__main__":
    unittest.main()
