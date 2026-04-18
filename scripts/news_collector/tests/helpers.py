from __future__ import annotations

import json


class FakeResponse:
    def __init__(self, *, text: str = "", status_code: int = 200, json_data=None):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code
        self._json_data = json_data
        self.is_success = status_code < 400

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_data is not None:
            return self._json_data
        return json.loads(self.text)


class FakeClient:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, url, params=None):
        key = url if params is None else (url, tuple(sorted(params.items())))
        response = self.mapping.get(key)
        if response is None:
            response = self.mapping.get(url)
        if response is None:
            raise AssertionError(f"Unexpected request: {url!r} params={params!r}")
        return response

    def post(self, url, json=None, headers=None):
        key = (url, "POST")
        response = self.mapping.get(key)
        if response is None:
            response = self.mapping.get(url)
        if response is None:
            raise AssertionError(f"Unexpected POST request: {url!r} json={json!r} headers={headers!r}")
        return response
