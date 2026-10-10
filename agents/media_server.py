"""Yerel medya sunucusu: e-postadaki "Dinle" bağlantısının bu Mac'te tıklanınca açılması için.

Yalnızca 127.0.0.1 (bu bilgisayar) üzerinden dinler; ağdaki diğer cihazlar erişemez. Yalnızca
`output/` altındaki ses/video dosyalarını (.mp3, .mp4, .m4a) sunar; diğer dosyalar 404 döner.

Zamanlayıcı (`main.py --schedule`) bunu arka planda kendiliğinden başlatır. Elle:
    python -m agents.media_server
"""
from __future__ import annotations

import logging
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from config import Settings, get_settings

log = logging.getLogger("media.server")

ALLOWED_SUFFIXES = {".mp3", ".mp4", ".m4a"}


class MediaHandler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if Path(self.path.split("?", 1)[0]).suffix.lower() not in ALLOWED_SUFFIXES:
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        if Path(self.path.split("?", 1)[0]).suffix.lower() not in ALLOWED_SUFFIXES:
            self.send_error(404)
            return
        super().do_HEAD()

    def list_directory(self, path):  # klasör listesi gösterilmez
        self.send_error(404)
        return None

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


def make_server(settings: Settings) -> ThreadingHTTPServer:
    handler = partial(MediaHandler, directory=str(settings.output_dir))
    return ThreadingHTTPServer(("127.0.0.1", settings.media_server_port), handler)


def start_in_background(settings: Optional[Settings] = None) -> Optional[ThreadingHTTPServer]:
    """Sunucuyu arka plan iş parçacığında başlatır. Port doluysa (ör. zaten çalışıyorsa) None döner."""
    settings = settings or get_settings()
    try:
        server = make_server(settings)
    except OSError as exc:
        log.warning("Medya sunucusu başlatılamadı (port %s): %s", settings.media_server_port, exc)
        return None
    threading.Thread(target=server.serve_forever, name="media-server", daemon=True).start()
    log.info("Medya sunucusu: http://localhost:%s → %s", settings.media_server_port, settings.output_dir)
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    s = get_settings()
    srv = make_server(s)
    print(f"Medya sunucusu çalışıyor: http://localhost:{s.media_server_port}  (durdurmak için Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
