"""Run the website: python -m tutor.web"""

import logging

import uvicorn

from ..config import Settings
from .app import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    uvicorn.run(create_app(settings=settings), host=settings.web_host, port=settings.web_port)


if __name__ == "__main__":
    main()
