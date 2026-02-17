"""Lightweight MCP Bus testing scaffold for unit and integration tests.

This module provides two small test helpers used by unit tests:

- MCPStubServer: an in-process, thread-backed HTTP server that implements a
  minimal subset of the production MCP Bus API (/register, /agents, /call,
  /health). Tests can program custom handlers for (agent, tool) pairs or
  instruct the stub to forward /call requests to a real HTTP agent endpoint.

- AgentServer: a tiny test HTTP server that can be used to simulate a
  registered agent with one or more tool endpoints (POST-based).

Both servers use only the Python standard library so they are fast and
reliable in CI. Tests should prefer the pytest fixture `mcp_server` (defined
in `tests/conftest.py`) which starts the stub and patches `requests.get`
/ `requests.post` so existing client code can use `requests` without special
handling. When writing tests that should avoid `requests` entirely you can
also use the helper functions `http_get` and `http_post` that use
`urllib.request` directly.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


class MCPStubServer:
    """A tiny, in-process MCP Bus stub used for tests.

    Usage:
        server = MCPStubServer()
        server.start()
        try:
            # program behavior
            server.add_handler('my_agent', 'echo', lambda args, kwargs: {'ok': True})
            # call via http_post(server.url() + '/call', payload)
        finally:
            server.stop()
    """

    def __init__(self, forward_calls: bool = False):
        self._agents: dict[str, str] = {}
        self._handlers: dict[
            tuple[str, str], Callable[[list[Any], dict[str, Any]], Any]
        ] = {}
        self._calls: list[dict[str, Any]] = []
        self.forward_calls = forward_calls

        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None
        self.base_url: str | None = None

    # --- Public helpers ---
    def start(self) -> None:
        Handler = self._make_handler()

        class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.allow_reuse_address = True
        self._server = server
        self.port = server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"

        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

        # Small safety sleep to ensure accept loop is running on CI
        time.sleep(0.02)

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)

        self._server = None
        self._thread = None
        self.port = None
        self.base_url = None

    def add_handler(
        self, agent: str, tool: str, fn: Callable[[list[Any], dict[str, Any]], Any]
    ) -> None:
        """Register a custom handler for (agent, tool). Handler receives
        (args, kwargs) and can return either a JSON-serializable object or a
        (status_code, object) tuple to control response code.
        """
        self._handlers[(agent, tool)] = fn

    def register_agent(self, name: str, address: str) -> None:
        """Register an agent in the stub without using HTTP (convenience).
        Tests that want to exercise the full HTTP path should POST to
        /register instead (see http_post helper).
        """
        self._agents[name] = address

    def url(self) -> str:
        assert self.base_url is not None, "server not started"
        return self.base_url

    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    # --- Internal ---
    def _make_handler(self):
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = "MCPStub/0.1"
            sys_version = ""

            def log_message(
                self, format: str, *args: object
            ) -> None:  # silence std err noise in CI
                return

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length:
                    raw = self.rfile.read(length).decode("utf-8")
                    try:
                        return json.loads(raw)
                    except Exception:
                        return {}
                return {}

            def _write_json(self, code: int, obj: Any) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(obj).encode("utf-8"))

            def do_GET(self) -> None:
                if self.path.rstrip("/") == "/agents":
                    self._write_json(200, parent._agents.copy())
                    return
                if self.path.rstrip("/") == "/health":
                    self._write_json(200, {"status": "ok"})
                    return
                self._write_json(404, {"error": "not found"})

            def do_POST(self) -> None:
                if self.path.rstrip("/") == "/register":
                    payload = self._read_json()
                    name = payload.get("name")
                    address = payload.get("address")
                    if not name or not address:
                        self._write_json(400, {"error": "invalid payload"})
                        return
                    parent._agents[name] = address
                    parent._calls.append(
                        {"type": "register", "name": name, "address": address}
                    )
                    self._write_json(200, {"status": "ok"})
                    return

                if self.path.rstrip("/") == "/call":
                    payload = self._read_json()
                    agent = payload.get("agent")
                    tool = payload.get("tool")
                    args = payload.get("args", [])
                    kwargs = payload.get("kwargs", {})
                    parent._calls.append(
                        {
                            "type": "call",
                            "agent": agent,
                            "tool": tool,
                            "args": args,
                            "kwargs": kwargs,
                        }
                    )

                    if agent not in parent._agents:
                        self._write_json(404, {"error": f"agent not found: {agent}"})
                        return

                    key = (agent, tool)
                    if key in parent._handlers:
                        try:
                            result = parent._handlers[key](args, kwargs)
                        except Exception as e:
                            self._write_json(500, {"error": str(e)})
                            return
                        if (
                            isinstance(result, tuple)
                            and len(result) == 2
                            and isinstance(result[0], int)
                        ):
                            status_code, data = result
                            self._write_json(status_code, data)
                        else:
                            self._write_json(200, result)
                        return

                    if parent.forward_calls:
                        address = parent._agents[agent]
                        # Build destination URL: join address and tool path safely
                        if not address.endswith("/") and not tool.startswith("/"):
                            url = address + "/" + tool
                        else:
                            url = address.rstrip("/") + "/" + tool.lstrip("/")
                        try:
                            req = urllib.request.Request(
                                url,
                                data=json.dumps(
                                    {"args": args, "kwargs": kwargs}
                                ).encode("utf-8"),
                                headers={"Content-Type": "application/json"},
                            )
                            with urllib.request.urlopen(req, timeout=5) as resp:
                                body = resp.read().decode("utf-8")
                                try:
                                    data = json.loads(body)
                                    self._write_json(resp.getcode(), data)
                                except Exception:
                                    self._write_json(resp.getcode(), {"text": body})
                            return
                        except Exception as e:
                            self._write_json(502, {"error": str(e)})
                            return

                    # Default: echo the payload back
                    self._write_json(
                        200, {"status": "ok", "echo": {"args": args, "kwargs": kwargs}}
                    )
                    return

                self._write_json(404, {"error": "not found"})

        return Handler


class AgentServer:
    """Tiny HTTP server used to simulate a registered agent.

    Add handlers keyed by the path (no leading slash) — each handler is a
    function (args, kwargs) -> JSON-serializable object. Example:

        agent = AgentServer()
        agent.add_tool('echo', lambda args, kwargs: {'echo': args})
        agent.start()
        # register lowercase address with MCP stub
    """

    def __init__(self):
        self._handlers: dict[str, Callable[[list[Any], dict[str, Any]], Any]] = {}
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None
        self.base_url: str | None = None

    def add_tool(
        self, name: str, fn: Callable[[list[Any], dict[str, Any]], Any]
    ) -> None:
        self._handlers[name.strip("/")] = fn

    def start(self) -> None:
        Handler = self._make_handler()

        class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.allow_reuse_address = True
        self._server = server
        self.port = server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        time.sleep(0.01)

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)
        self._server = None
        self._thread = None
        self.port = None
        self.base_url = None

    def url(self) -> str:
        assert self.base_url is not None
        return self.base_url

    def _make_handler(self):
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = "AgentServer/0.1"
            sys_version = ""

            def log_message(self, format: str, *args: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0) or 0)
                payload = {}
                if length:
                    raw = self.rfile.read(length).decode("utf-8")
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        payload = {}
                path = self.path.strip("/")
                handler = parent._handlers.get(path)
                if not handler:
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({"error": "unknown tool"}).encode("utf-8")
                    )
                    return
                try:
                    result = handler(payload.get("args", []), payload.get("kwargs", {}))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode("utf-8"))
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

        return Handler


def http_post(
    url: str, payload: dict[str, Any], timeout: float = 5.0
) -> tuple[int, Any]:
    """Helper that posts JSON using urllib and returns (status_code, parsed_json)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        try:
            return resp.getcode(), json.loads(raw)
        except Exception:
            return resp.getcode(), {"text": raw}
