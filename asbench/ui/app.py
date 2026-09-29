"""Starts the app."""

from __future__ import annotations

import sys

from asbench import APP_NAME


def run_gui(args) -> int:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    from asbench.ui import theme
    from asbench.ui.controller import Controller
    from asbench.ui.window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")  # the stylesheet provides the look; Fusion renders it the same everywhere
    settings = QSettings(APP_NAME, APP_NAME)
    theme.install(app, settings.value("theme", "auto", type=str))

    ctl = Controller(quick=args.quick, storage_path=args.storage_path or "", power=not args.no_power)
    window = MainWindow(ctl)
    window.show()
    return app.exec()
