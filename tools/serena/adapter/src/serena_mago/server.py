"""Bridge full document sync and UTF-16 wire positions to SolidLSP's Python indices.

No semantic answers are synthesized: requests, symbol ranges, references and edits
come from the actual Mago process. The protocol trace retains the wire values.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import re
import threading
from urllib.parse import unquote, urlparse

from solidlsp.dependency_provider import LanguageServerDependencyProvider
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_process import StdioLanguageServer

log = logging.getLogger(__name__)


class MagoDependency(LanguageServerDependencyProvider):
    def create_launch_command(self):
        binary = os.environ.get("MAGO_BINARY", "mago")
        resolved = shutil.which(binary)
        if not resolved:
            raise FileNotFoundError(f"Mago executable {binary!r} missing; run ./bin/poc up to build the pinned backend")
        identity = Path("/opt/toolchain-runtime.json")
        if identity.exists():
            expected = json.loads(identity.read_text())["mago_binary_sha256"]
            actual = hashlib.sha256(Path(resolved).read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError(f"Mago binary identity mismatch: {resolved}")
        return [resolved, "language-server"]

    def create_launch_command_env(self):
        return {"MAGO_EXPERIMENTAL_SERVER": "1"}


def convert_character(text, line_number, column, *, wire=False):
    """Translate one valid LSP line position; only CR, LF and CRLF end lines.

    Python buffer columns count Unicode code points; Mago wire columns count
    UTF-16 units. Beyond-EOL columns clamp as LSP specifies. A split surrogate
    is refused rather than silently moving an edit. No text/newline is rewritten.
    """
    if type(line_number) is not int or type(column) is not int or line_number < 0 or column < 0:
        raise ValueError("Position requires non-negative integer line and character")
    lines = re.split(r"\r\n|\r|\n", text)
    if line_number >= len(lines):
        raise ValueError(f"Position line {line_number} exceeds document EOF")
    line = lines[line_number]
    if wire:
        return len(line[:column].encode("utf-16-le")) // 2
    return len(line.encode("utf-16-le")[:column * 2].decode("utf-16-le", errors="strict"))


class MagoTransport(StdioLanguageServer):
    """Use SolidLSP's supported transport extension point, without patching it."""

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        # Only didOpen/didChange text is authoritative for an OPEN server buffer.
        # Closed files are never cached: each response reads a fresh disk snapshot,
        # including atomic replacements with unchanged or decreasing timestamps.
        self.documents = {}
        self.document_versions = {}
        self._state_lock = threading.RLock()
        self._state_trace_bytes = 0
        self._state_trace_truncated = False
        super().__init__(*args, **kwargs)

    def _disk_path(self, uri):
        parsed = urlparse(uri or "")
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise ValueError(f"Cannot convert position without a local file URI: {uri}")
        return Path(unquote(parsed.path))

    def _state_trace(self, event, uri=None, **extra):
        """Optional bounded hash-only document-state evidence; never log source text."""
        evidence = os.environ.get("POC_EVIDENCE")
        if os.environ.get("POC_TRACE") != "1" or not evidence:
            return
        record = {"event":event,"uri":uri,"pid":os.getpid(),**extra}
        if uri:
            try:
                raw = self._disk_path(uri).read_bytes()
                record["disk_bytes_sha256"] = hashlib.sha256(raw).hexdigest()
                normalized = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                record["disk_normalized_sha256"] = hashlib.sha256(normalized.encode()).hexdigest()
            except (OSError, UnicodeError) as exc:
                record["disk_error"] = type(exc).__name__
            transmitted = self.documents.get(uri)
            record["open"] = transmitted is not None
            record["version"] = self.document_versions.get(uri)
            record["transmitted_sha256"] = hashlib.sha256(transmitted.encode()).hexdigest() if transmitted is not None else None
        encoded = (json.dumps(record,ensure_ascii=True)+"\n").encode()
        with self._state_lock:
            if self._state_trace_truncated:
                return
            if self._state_trace_bytes + len(encoded) > 2_000_000:
                encoded = b'{"event":"trace_truncated","limit_bytes":2000000}\n'
                self._state_trace_truncated = True
            path = Path(evidence, f"document-state-{os.getpid()}.jsonl")
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("ab") as output:
                output.write(encoded)
            self._state_trace_bytes += len(encoded)

    def text(self, uri):
        with self._state_lock:
            if uri in self.documents:
                text = self.documents[uri]
            else:
                # read_text uses universal-newline normalization, matching SolidLSP
                # FileUtils. Missing/deleted files fail; old contents are never used.
                text = self._disk_path(uri).read_text(encoding="utf-8")
            self._state_trace("position_text", uri, selected_sha256=hashlib.sha256(text.encode()).hexdigest())
            return text

    def start(self):
        with self._state_lock:
            self.documents.clear()
            self.document_versions.clear()
        self._state_trace("server_start_clear")
        return super().start()

    def stop(self, timeout=5.0):
        try:
            return super().stop(timeout=timeout)
        finally:
            with self._state_lock:
                self.documents.clear()
                self.document_versions.clear()
            self._state_trace("server_stop_clear")

    def convert(self, value, uri=None, *, wire=False, _texts=None):
        if _texts is None:
            _texts = {}  # One immutable text snapshot per URI per conversion.
        if isinstance(value, list):
            return [self.convert(x, uri, wire=wire, _texts=_texts) for x in value]
        if not isinstance(value, dict):
            return value
        origin_uri = uri
        uri = value.get("uri", value.get("targetUri", value.get("textDocument", {}).get("uri", uri)))
        if "line" in value and "character" in value:
            if uri not in _texts:
                _texts[uri] = self.text(uri)
            col = convert_character(_texts[uri], value["line"], value["character"], wire=wire)
            return {**value, "character": col}
        result = {}
        for key, item in value.items():
            if key == "changes" and isinstance(item, dict):
                result[key] = {u: self.convert(edits, u, wire=wire, _texts=_texts) for u, edits in item.items()}
            else:
                # LocationLink.originSelectionRange belongs to the request file,
                # while targetRange/targetSelectionRange belong to targetUri.
                item_uri = origin_uri if key == "originSelectionRange" and "targetUri" in value else uri
                result[key] = self.convert(item, item_uri, wire=wire, _texts=_texts)
        return result

    def send_request(self, method, params=None):
        if method == "initialize":
            return super().send_request(method, params)
        uri = (params or {}).get("textDocument", {}).get("uri")
        self._state_trace("request", uri, method=method)
        response = super().send_request(method, self.convert(params, uri, wire=True))
        converted = self.convert(response, uri)
        self._state_trace("response_converted", uri, method=method)
        return converted

    def send_notification(self, method, params=None):
        if method in ("textDocument/didOpen", "textDocument/didChange"):
            uri = params["textDocument"]["uri"]
            if method.endswith("didOpen"):
                if uri in self.documents:
                    raise ValueError("Duplicate didOpen would diverge from Mago's accepted buffer")
                self.documents[uri] = params["textDocument"]["text"]
            else:
                if uri not in self.documents:
                    raise ValueError("didChange requires an open Mago document")
                previous_version = self.document_versions[uri]
                if params["textDocument"]["version"] <= previous_version:
                    raise ValueError("didChange version must increase; no state changed")
                changes = params["contentChanges"]
                if any("range" in x for x in changes):
                    text = self.owner.open_file_buffers[uri].contents
                    params = {**params, "contentChanges": [{"text": text}]}
                else:
                    text = changes[-1]["text"]
                self.documents[uri] = text
            self.document_versions[uri] = params["textDocument"].get("version")
            self._state_trace(method, uri)
        elif method == "textDocument/didClose":
            uri = params["textDocument"]["uri"]
            with self._state_lock:
                self.documents.pop(uri, None)
                self.document_versions.pop(uri, None)
            self._state_trace(method, uri)
        elif method == "workspace/didChangeWatchedFiles":
            for change in (params or {}).get("changes", []):
                uri = change["uri"]
                # Open buffer wins over filesystem events (including deletion).
                # Closed files have no cache, so changed/created/replaced files are
                # read from disk and deleted files fail on the next conversion.
                self._state_trace(method, uri, change_type=change["type"])
        super().send_notification(method, params)


class MagoServer(SolidLanguageServer):
    def __init__(self, config, repository_root_path, solidlsp_settings):
        super().__init__(config, repository_root_path, None, "php", solidlsp_settings)

    def _create_dependency_provider(self):
        return MagoDependency(self._custom_settings, self._ls_resources_dir)

    def _create_language_server_interface(self, logging_fn):
        return MagoTransport(
            self._get_process_launch_info(), owner=self, ls_id=self.ls_id,
            determine_log_level=self._determine_log_level, logger=logging_fn,
            start_independent_lsp_process=self.config.start_independent_lsp_process,
        )

    def _create_base_initialize_params(self):
        return {"capabilities": {
            "general": {"positionEncodings": ["utf-16"]},
            "textDocument": {
                "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                "definition": {"linkSupport": True},
                "synchronization": {"didSave": True},
            },
            "workspace": {"workspaceFolders": True, "workspaceEdit": {"documentChanges": True}},
        }}

    def _start_server(self):
        self.server.on_notification("window/logMessage", lambda p: log.info("Mago: %s", p))
        self.server.on_notification("textDocument/publishDiagnostics", lambda p: None)
        self.server.on_notification("$/progress", lambda p: None)
        self.server.on_request("client/registerCapability", lambda p: None)
        self.server.start()
        response = self.server.send.initialize(self._create_initialize_params())
        if response.get("serverInfo", {}).get("name") != "mago-server":
            raise RuntimeError("Selected process is not the Mago language server")
        self.capabilities = response["capabilities"]
        if self.capabilities.get("positionEncoding", "utf-16") != "utf-16":
            raise RuntimeError("Mago selected an unsupported position encoding")
        if self.capabilities.get("textDocumentSync", {}).get("change") != 1:
            raise RuntimeError("Pinned Mago must negotiate full document synchronization")
        if not self.capabilities.get("documentSymbolProvider"):
            raise RuntimeError("Mago did not advertise document symbols")
        self.server.notify.initialized({})
        # A restarted process has no buffers. Explicitly replay currently open
        # SolidLSP buffers after initialization, keeping their versions and text.
        for uri, buffer in self.open_file_buffers.items():
            self.server.send_notification("textDocument/didOpen", {"textDocument": {
                "uri":uri,"languageId":buffer.language_id,"version":buffer.version,"text":buffer.contents}})
        identity = {"backend": "mago", "pid": self.server._process._popen.pid,
                    "command": self._get_process_launch_info().cmd, "initialize": response,
                    "root": self.repository_root_path}
        log.info("MAGO_BACKEND_IDENTITY %s", json.dumps(identity))
        evidence = os.environ.get("POC_EVIDENCE")
        if evidence:
            Path(evidence).mkdir(parents=True, exist_ok=True)
            Path(evidence, f"backend-{identity['pid']}.json").write_text(json.dumps(identity, indent=2))

    def _observe_server_notification(self, method, params):
        if method == "textDocument/publishDiagnostics":
            params = self.server.convert(params)
        super()._observe_server_notification(method, params)

    def _supports_pull_diagnostics(self):
        return False

    def _accept_published_diagnostics(self, diagnostics):
        return True  # An empty publication is the evidence that an error cleared.

    def _get_published_diagnostics_wait_timeout(self, pull_diagnostics_failed):
        return 10.0

    def _get_wait_time_for_cross_file_referencing(self):
        return 0  # Mago bootstrap finishes inside initialize.

    def is_ignored_dirname(self, dirname):
        return super().is_ignored_dirname(dirname) or dirname in {"var", ".serena", ".phpunit.cache"}

    def request_symbol_references(self, relative_file_path, symbol, member=""):
        """Forward Mago's dependency graph, whose edges have no source positions.

        This is separate from textDocument/references and call hierarchy. The
        native server owns analysis generations and error attribution; no graph
        answers or fallback CLI analysis are constructed by the adapter.
        """
        if not isinstance(symbol, str) or not symbol or not isinstance(member, str):
            raise ValueError("Expected a symbol name and an optional member name")
        with self._open_file_context(relative_file_path) as file_buffer:
            if not (self.capabilities.get("experimental") or {}).get("symbolReferencesProvider"):
                raise RuntimeError("Selected Mago server does not support dependency graph queries")
            result = self.server.send_request("mago/symbolReferences", {
                "textDocument": {"uri": file_buffer.uri}, "symbol": symbol, "member": member,
            })
        if not isinstance(result, dict) or not isinstance(result.get("references"), list):
            raise RuntimeError("Malformed Mago dependency graph response")
        return result

    def request_rename_symbol_edit(self, relative_file_path, line, column, new_name):
        # Keep the request document open until validation is complete. The base
        # request closes its own context before returning the WorkspaceEdit.
        with self.open_file(relative_file_path):
            edit = super().request_rename_symbol_edit(relative_file_path, line, column, new_name)
            for change in (edit or {}).get("documentChanges", []):
                if "textDocument" not in change:
                    raise ValueError("Mago resource operations are unsupported; no edits applied")
                doc = change["textDocument"]
                buffer = self.open_file_buffers.get(doc["uri"])
                if doc.get("version") is not None and (buffer is None or doc["version"] != buffer.version):
                    raise ValueError("Stale Mago WorkspaceEdit document version; no edits applied")
            return edit
