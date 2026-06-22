"""Application entry point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv  # type: ignore[import-untyped]
from PyQt6.QtWidgets import QApplication

from fw_obd.db.database import Database
from fw_obd.ui.main_window import MainWindow

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting Firewall OBD")

    db = Database()
    app = QApplication(sys.argv)
    app.setApplicationName("Firewall OBD")
    app.setApplicationVersion("0.1.0")

    window = MainWindow(db)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
