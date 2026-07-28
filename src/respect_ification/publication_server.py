# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import argparse
import hashlib
import http.server
import json
import ssl
from functools import partial
from pathlib import Path
from typing import Dict, Optional, Type
from urllib.parse import urlsplit


def _deployment(pack: Path) -> Dict[str, object]:
    value = json.loads(
        (pack / "deployment.json").read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise ValueError("deployment metadata must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_publication_handler(
    pack: Path,
) -> Type[http.server.SimpleHTTPRequestHandler]:
    pack = pack.resolve(strict=True)
    public = pack / "public"
    if not public.is_dir():
        raise ValueError("publication pack has no public directory")
    deployment = _deployment(pack)
    media_types = deployment.get("media_types")
    if not isinstance(media_types, dict):
        raise ValueError("deployment metadata has no media-type map")

    class PublicationHandler(http.server.SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        current_etag: Optional[str] = None

        def end_headers(self) -> None:
            if self.current_etag is not None:
                self.send_header("ETag", self.current_etag)
            self.send_header(
                "Cache-Control",
                "public, max-age=0, no-transform",
            )
            self.send_header("Content-Encoding", "identity")
            super().end_headers()

        def guess_type(self, path: str) -> str:
            request_path = urlsplit(self.path).path
            declared = media_types.get(request_path)
            if isinstance(declared, str):
                return declared
            return super().guess_type(path)

        def send_head(self):
            self.current_etag = None
            path = Path(self.translate_path(self.path))
            if not path.is_file():
                return super().send_head()
            etag = '"' + _sha256(path) + '"'
            self.current_etag = etag
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.end_headers()
                return None
            return super().send_head()

    return partial(PublicationHandler, directory=str(public))


def serve_publication_pack(
    pack: Path,
    *,
    bind: str,
    port: int,
    certfile: Optional[Path] = None,
    keyfile: Optional[Path] = None,
) -> None:
    if (certfile is None) != (keyfile is None):
        raise ValueError("certificate and key must be supplied together")
    server = http.server.ThreadingHTTPServer(
        (bind, port),
        make_publication_handler(pack),
    )
    if certfile is not None and keyfile is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve a generated RESPECT Publication Pack."
    )
    parser.add_argument("--pack", type=Path, default=Path(__file__).parent)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--certfile", type=Path)
    parser.add_argument("--keyfile", type=Path)
    args = parser.parse_args()
    try:
        serve_publication_pack(
            args.pack,
            bind=args.bind,
            port=args.port,
            certfile=args.certfile,
            keyfile=args.keyfile,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
