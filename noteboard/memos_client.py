"""Minimal Memos v1 REST client (stdlib only, no Qt). Speaks the API of
Memos 0.30; timestamps are converted to unix ms at this boundary so the rest
of the app never sees RFC3339."""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS = timedelta(milliseconds=1)
_STATES = ("NORMAL", "ARCHIVED")
_VISIBILITIES = ("PRIVATE", "PROTECTED", "PUBLIC")


class MemosError(Exception):
    """Base class; str() is safe to show in the UI."""


class AuthError(MemosError):
    pass


class NotFoundError(MemosError):
    pass


class NetworkError(MemosError):
    pass


class ApiError(MemosError):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class RemoteMemo:
    id: str                 # "memos/{id}" without the prefix
    content: str
    pinned: bool
    state: str
    visibility: str
    create_time: int        # unix ms
    update_time: int        # unix ms; compared by equality, never ordering


def parse_time(value: str) -> int:
    # fromisoformat takes Z and fractional seconds; the server may send
    # nanosecond digits, which it truncates to microseconds.
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Floor, not round: format_time/parse_time must round-trip ms exactly.
    return (dt - _EPOCH) // _MS


def format_time(ms: int) -> str:
    dt = _EPOCH + ms * _MS
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def _memo_id(name: str) -> str:
    return name.removeprefix("memos/")


def _to_remote(d: dict) -> RemoteMemo:
    state = d.get("state")
    visibility = d.get("visibility")
    return RemoteMemo(
        id=_memo_id(d["name"]),
        content=d.get("content", ""),
        pinned=bool(d.get("pinned", False)),
        state=state if state in _STATES else "NORMAL",
        visibility=visibility if visibility in _VISIBILITIES else "PRIVATE",
        create_time=parse_time(d["createTime"]),
        update_time=parse_time(d["updateTime"]),
    )


_FIELD_NAMES = {"content": "content", "pinned": "pinned", "state": "state",
                "visibility": "visibility", "create_time": "createTime"}


def _to_body(fields: dict) -> dict:
    body = {}
    for key, value in fields.items():
        if key == "create_time":
            value = format_time(value)
        body[_FIELD_NAMES[key]] = value
    return body


class MemosClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 15,
                 page_size: int = 200):
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._page_size = page_size
        self._user: str | None = None

    def _request(self, method: str, path: str, *, query: dict | None = None,
                 body: dict | None = None) -> dict:
        url = f"{self._base}/api/v1/{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise self._http_error(e) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise NetworkError(f"Cannot reach {self._base}: {reason}") from None
        try:
            return json.loads(raw) if raw.strip() else {}
        except ValueError:
            raise ApiError(f"Unexpected response from {self._base} (not JSON)",
                           200) from None

    @staticmethod
    def _http_error(e: urllib.error.HTTPError) -> MemosError:
        try:
            detail = json.loads(e.read()).get("message") or ""
        except (ValueError, AttributeError, OSError):
            detail = ""
        e.close()
        suffix = f": {detail}" if detail else ""
        if e.code in (401, 403):
            return AuthError(f"Server rejected the access token (HTTP {e.code}){suffix}")
        if e.code == 404:
            return NotFoundError(f"Not found (HTTP 404){suffix}")
        return ApiError(f"Server error HTTP {e.code}{suffix}", e.code)

    def _current_user(self) -> str:
        if self._user is None:
            name = self._request("GET", "auth/me").get("user", {}).get("name")
            if not name:
                raise AuthError("Access token does not belong to a user")
            self._user = name
        return self._user

    def list_all(self) -> list[RemoteMemo]:
        """Every memo of the token's user, both states, all pages. Raises if
        any page fails: a partial list would look like server-side deletes."""
        # Without the creator filter the server also returns other users'
        # public memos.
        creator = f'creator == "{self._current_user()}"'
        out = []
        for state in _STATES:
            token = ""
            while True:
                query = {"pageSize": self._page_size, "state": state,
                         "filter": creator}
                if token:
                    query["pageToken"] = token
                page = self._request("GET", "memos", query=query)
                out.extend(_to_remote(m) for m in page.get("memos", []))
                token = page.get("nextPageToken", "")
                if not token:
                    break
        return out

    def get(self, memo_id: str) -> RemoteMemo:
        return _to_remote(self._request("GET", f"memos/{memo_id}"))

    def create(self, fields: dict, memo_id: str | None = None) -> RemoteMemo:
        """fields: content, pinned, state, visibility, create_time (unix ms)."""
        query = {"memoId": memo_id} if memo_id else None
        return _to_remote(self._request(
            "POST", "memos", query=query, body=_to_body(fields)))

    def update(self, memo_id: str, fields: dict) -> RemoteMemo:
        """PATCH only the given fields; the mask is derived from them so
        attachments and relations on the server are never touched."""
        body = _to_body(fields)
        body["name"] = f"memos/{memo_id}"
        return _to_remote(self._request(
            "PATCH", f"memos/{memo_id}",
            query={"updateMask": ",".join(_FIELD_NAMES[k] for k in fields)},
            body=body))

    def delete(self, memo_id: str) -> None:
        self._request("DELETE", f"memos/{memo_id}")
