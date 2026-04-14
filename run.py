import os
from wsgiref.simple_server import make_server

from app.config import AppConfig
from app.web import create_app


def main():
    config = AppConfig.from_env()
    app = create_app(config)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving Deep Work 4DX on http://127.0.0.1:{port}")
    with make_server(host, port, app) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
