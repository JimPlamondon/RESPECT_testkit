# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.parse
import urllib.request
from typing import Any, Dict


_QUERY_EXPRESSION = r"""
((selector) => {
  const normalizedText = (value) =>
    String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  const visible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none"
      && style.visibility !== "hidden"
      && Number(style.opacity) > 0
      && rect.width > 0
      && rect.height > 0
      && rect.right > 0
      && rect.bottom > 0
      && rect.left < innerWidth
      && rect.top < innerHeight;
  };
  const roots = [document];
  const elements = [];
  while (roots.length) {
    const root = roots.shift();
    for (const element of root.querySelectorAll("*")) {
      elements.push(element);
      if (element.shadowRoot) roots.push(element.shadowRoot);
    }
  }
  const matches = elements.filter((element) => {
    if (selector.tag_name
        && element.localName.toLowerCase() !== selector.tag_name.toLowerCase()) {
      return false;
    }
    if (selector.text
        && normalizedText(element.innerText) !== normalizedText(selector.text)) {
      return false;
    }
    if (selector.attribute
        && element.getAttribute(selector.attribute.name)
          !== selector.attribute.value) {
      return false;
    }
    return visible(element);
  }).map((element) => {
    const rect = element.getBoundingClientRect();
    return {
      tag_name: element.localName,
      text: normalizedText(element.innerText).slice(0, 256),
      attribute_value: selector.attribute
        ? element.getAttribute(selector.attribute.name)
        : null,
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
      width: rect.width,
      height: rect.height
    };
  });
  return {
    page_url: location.href,
    page_title: document.title,
    viewport_width: innerWidth,
    viewport_height: innerHeight,
    matches
  };
})(%s)
"""


def _read_exact(connection: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise RuntimeError("WebView DevTools connection closed unexpectedly")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class _WebSocket:
    def __init__(self, url: str, timeout: float) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("WebView DevTools WebSocket must use local loopback")
        port = parsed.port
        if port is None:
            raise ValueError("WebView DevTools WebSocket port is missing")
        self._connection = socket.create_connection(
            (parsed.hostname, port),
            timeout=timeout,
        )
        self._connection.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).encode("ascii")
        self._connection.sendall(request)
        response = b""
        while b"\r\n\r\n" not in response:
            response += self._connection.recv(4096)
            if len(response) > 32_768:
                raise RuntimeError("WebView DevTools handshake exceeded bounded size")
        header = response.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1")
        expected = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        ).decode("ascii")
        if (
            not header.startswith("HTTP/1.1 101 ")
            or f"Sec-WebSocket-Accept: {expected}".lower() not in header.lower()
        ):
            raise RuntimeError("WebView DevTools WebSocket handshake failed")

    def close(self) -> None:
        try:
            try:
                self._send_frame(0x8, b"")
            except OSError:
                pass
        finally:
            self._connection.close()

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        length = len(payload)
        if length <= 125:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length <= 65_535:
            header = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack("!H", length)
        else:
            header = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack("!Q", length)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self._connection.sendall(header + mask + masked)

    def send_json(self, value: Dict[str, Any]) -> None:
        self._send_frame(
            0x1,
            json.dumps(value, separators=(",", ":")).encode("utf-8"),
        )

    def receive_json(self) -> Dict[str, Any]:
        fragments = []
        message_opcode = None
        while True:
            first, second = _read_exact(self._connection, 2)
            final = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", _read_exact(self._connection, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", _read_exact(self._connection, 8))[0]
            if length > 4 * 1024 * 1024:
                raise RuntimeError("WebView DevTools message exceeded bounded size")
            mask = _read_exact(self._connection, 4) if masked else b""
            payload = _read_exact(self._connection, length)
            if masked:
                payload = bytes(
                    value ^ mask[index % 4]
                    for index, value in enumerate(payload)
                )
            if opcode == 0x8:
                raise RuntimeError("WebView DevTools closed before replying")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode in {0x1, 0x2}:
                message_opcode = opcode
                fragments = [payload]
            elif opcode == 0x0 and message_opcode is not None:
                fragments.append(payload)
            else:
                continue
            if not final:
                continue
            if message_opcode != 0x1:
                raise RuntimeError("WebView DevTools returned a non-text message")
            value = json.loads(b"".join(fragments).decode("utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError("WebView DevTools response was not an object")
            return value


def _command(
    connection: _WebSocket,
    identifier: int,
    method: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    connection.send_json(
        {"id": identifier, "method": method, "params": params}
    )
    while True:
        response = connection.receive_json()
        if response.get("id") != identifier:
            continue
        if "error" in response or not isinstance(response.get("result"), dict):
            raise RuntimeError(f"WebView DevTools command failed: {method}")
        return response["result"]


def tap_visible_webview_element(
    port: int,
    selector: Dict[str, Any],
    *,
    timeout_ms: int,
) -> Dict[str, Any]:
    timeout = max(1.0, timeout_ms / 1000 + 1.0)
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json",
        timeout=timeout,
    ) as response:
        targets = json.loads(response.read(1024 * 1024).decode("utf-8"))
    pages = []
    for item in targets:
        if (
            not isinstance(item, dict)
            or item.get("type") != "page"
            or not isinstance(item.get("webSocketDebuggerUrl"), str)
        ):
            continue
        try:
            description = json.loads(item.get("description", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(description, dict) and description.get("visible") is True:
            pages.append(item)
    if len(pages) != 1:
        raise RuntimeError(
            "WebView action requires exactly one visible debuggable page"
        )
    connection = _WebSocket(pages[0]["webSocketDebuggerUrl"], timeout)
    try:
        expression = _QUERY_EXPRESSION % json.dumps(
            selector,
            sort_keys=True,
            separators=(",", ":"),
        )
        deadline = time.monotonic() + timeout_ms / 1000
        identifier = 1
        while True:
            evaluated = _command(
                connection,
                identifier,
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": False,
                },
            )
            identifier += 1
            result = evaluated.get("result")
            value = result.get("value") if isinstance(result, dict) else None
            if not isinstance(value, dict) or not isinstance(
                value.get("matches"), list
            ):
                raise RuntimeError(
                    "WebView selector did not return bounded match data"
                )
            matches = value["matches"]
            if len(matches) == 1:
                break
            if len(matches) > 1:
                raise RuntimeError(
                    "WebView selector matched more than one visible element"
                )
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "WebView selector did not match a visible element before timeout"
                )
            time.sleep(0.1)
        match = matches[0]
        if (
            not isinstance(match, dict)
            or not all(
                isinstance(match.get(key), (int, float))
                for key in ("x", "y", "width", "height")
            )
            or match["width"] <= 0
            or match["height"] <= 0
        ):
            raise RuntimeError("WebView selector returned invalid element geometry")
        point = {"x": match["x"], "y": match["y"]}
        _command(
            connection,
            identifier,
            "Input.dispatchTouchEvent",
            {
                "type": "touchStart",
                "touchPoints": [{**point, "radiusX": 1, "radiusY": 1}],
            },
        )
        _command(
            connection,
            identifier + 1,
            "Input.dispatchTouchEvent",
            {"type": "touchEnd", "touchPoints": []},
        )
        return {
            "kind": "webview_element_tapped",
            "success": True,
            "page_origin": urllib.parse.urlparse(
                str(value.get("page_url", ""))
            ).scheme
            + "://"
            + urllib.parse.urlparse(str(value.get("page_url", ""))).netloc,
            "page_path_sha256": hashlib.sha256(
                urllib.parse.urlparse(
                    str(value.get("page_url", ""))
                ).path.encode("utf-8")
            ).hexdigest(),
            "page_title_sha256": hashlib.sha256(
                str(value.get("page_title", "")).encode("utf-8")
            ).hexdigest(),
            "viewport_width": value.get("viewport_width"),
            "viewport_height": value.get("viewport_height"),
            "selector_sha256": hashlib.sha256(
                json.dumps(
                    selector,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "matched_element": {
                key: match.get(key)
                for key in ("tag_name", "x", "y", "width", "height")
            },
        }
    finally:
        connection.close()
