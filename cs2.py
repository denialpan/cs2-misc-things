from pathlib import Path
import argparse
import configparser
from datetime import datetime
import html
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile


APP_TITLE = "CS2 Launcher"
SETTINGS_FILE = Path(__file__).resolve().parent / "settings.ini"
AUTOJOINER_INTERVAL_SECONDS = 1.5
AUTOJOINER_PLAYER_LIMIT = 62
AUTOJOINER_CONNECT_ATTEMPT_SECONDS = 10
CONSOLE_MAX_LINES = 1000

ZIP_FIELDS = [
    ("metamod", "mmsource"),
    ("metamod launcher", "launcher"),
    ("cs2fixes", "Windows"),
    ("strippercs2", "StripperCS2"),
    ("gfl cs2 ze configs", "CS2-ZE-Configs"),
]

CS2FIXES_LINKS = {
    "cs2fixes.cfg": "https://pastebin.com/NUNWgZAY",
    "metamod": "https://www.metamodsource.net/downloads.php?branch=dev",
    "metamod launcher": "https://github.com/Poggicek/metamod-launcher/releases",
    "cs2fixes": "https://github.com/Source2ZE/CS2Fixes/releases",
    "strippercs2": "https://github.com/Source2ZE/StripperCS2/releases",
    "gfl cs2 ze configs": "https://github.com/gflze/CS2-ZE-Configs/",
}

CS2_FOLDER_NAME = "Counter-Strike Global Offensive"
GAMEINFO_WORKSHOP_FILTER_LINES = (
    '"substr" "agents/models/"',
    '"substr" "weapons/models/"',
)
GAMEINFO_WORKSHOP_BACKUP = "gameinfo.gi.cs2launcher-workshop-lines.json"
CSGO_INSTALLS = [
    ("metamod", "metamod", Path("game/csgo"), None, None),
    ("metamod launcher", "metamod launcher", Path("game/bin/win64"), None, None),
    ("cs2fixes", "cs2fixes", Path("game/csgo"), None, None),
    ("strippercs2", "strippercs2", Path("game/csgo"), None, None),
    (
        "gfl cs2 ze configs",
        "gfl cs2 ze configs",
        Path("game/csgo/addons/StripperCS2/maps"),
        "CS2-ZE-Configs-main/stripper/",
        None,
    ),
    (
        "gfl cs2 ze configs",
        "gfl cs2 ze configs entwatch",
        Path("game/csgo/addons/cs2fixes/configs/entwatch/maps"),
        "CS2-ZE-Configs-main/entwatch/",
        None,
    ),
    (
        "gfl cs2 ze configs",
        "gfl cs2 ze configs cs2fixes",
        Path("game/csgo/addons/cs2fixes/configs"),
        "CS2-ZE-Configs-main/cs2fixes/",
        ["CS2-ZE-Configs-main/entwatch/"],
    ),
    (
        "gfl cs2 ze configs",
        "gfl cs2 ze configs bosshud",
        Path("game/csgo/addons/cs2fixes/configs/bosshud"),
        "CS2-ZE-Configs-main/bosshud/",
        ["CS2-ZE-Configs-main/entwatch/"],
    ),
    (
        "gfl cs2 ze configs",
        "gfl cs2 ze configs mapcfg",
        Path("game/csgo/cfg/cs2fixes/maps"),
        "CS2-ZE-Configs-main/mapcfg/",
        None,
    ),
]

ZIP_REQUIRED_FILES = {
    "metamod": "addons/metamod/bin/win64/metamod.2.cs2.dll",
    "cs2fixes": "addons/cs2fixes/bin/win64/cs2fixes.dll",
    "strippercs2": "addons/StripperCS2/bin/StripperCS2.dll",
}

ADMINS_TEMPLATE = """
{
  "Groups":
  {
    "": // Set any Group Name you like
    {
      "flags": "z", // Root, grants all flags
      "immunity": 2 // Ignoring any immunity
    }
  },

  "Admins":
  {
    "<id here>": // Set your SteamID64 here
    {
      "name": "", // Set to anything you want
      "groups":
      [
        "" // Use the Group Name you set in the Groups object above.
      ],
      "flags": "z", // Root, grants all flags
      "immunity": 2 // Ignoring any immunity
    }
  }
}
"""

def launch_gui():
    try:
        from PySide6.QtCore import QObject, Signal
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QFileDialog,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSizePolicy,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as error:
        print("PySide6 is required for the GUI. Install it with: pip install PySide6", file=sys.stderr)
        print(error, file=sys.stderr)
        return 1

    class LogBridge(QObject):
        message = Signal(str)
        autojoiner_stopped = Signal()

    class PathSelector(QWidget):
        def __init__(
            self,
            label_text,
            initial_path="",
            mode="file",
            file_filter="All files (*.*)",
            detect_callback=None,
            link_url=None,
        ):
            super().__init__()
            self.setFixedHeight(30)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.mode = mode
            self.file_filter = file_filter
            self.detect_callback = detect_callback

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.setSpacing(4)

            label = QLabel()
            if link_url:
                label.setText(f'<a style="color: white;" href="{link_url}">{label_text.lower()}</a>')
                label.setOpenExternalLinks(True)
                label.setToolTip(link_url)
                label.setStyleSheet("QLabel { color: white; }")
            else:
                label.setText(label_text.lower())
            label.setFixedWidth(130)
            self.entry = QLineEdit(initial_path)
            self.entry.setMinimumWidth(320)
            self.entry.setFixedHeight(26)
            self.entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(label, 0)
            layout.addWidget(self.entry, 1)

            if detect_callback:
                detect = QPushButton("Auto-detect")
                detect.setMinimumWidth(92)
                detect.setFixedHeight(26)
                detect.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
                detect.clicked.connect(self.auto_detect)
                layout.addWidget(detect)

            browse = QPushButton("Browse...")
            browse.setMinimumWidth(84)
            browse.setFixedHeight(26)
            browse.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            browse.clicked.connect(self.browse)
            layout.addWidget(browse)

        def auto_detect(self):
            detected_path = self.detect_callback() if self.detect_callback else ""
            if detected_path:
                self.entry.setText(detected_path)
                QMessageBox.information(self, "CS2 root detected", f"Found CS2 root directory:\n{detected_path}")
            else:
                QMessageBox.critical(self, "CS2 root not found", "Could not automatically locate the CS2 root directory.")

        def browse(self):
            if self.mode == "directory":
                selected = QFileDialog.getExistingDirectory(self, "Select CS2 root directory")
            else:
                selected, _ = QFileDialog.getOpenFileName(self, "Select file", "", self.file_filter)

            if selected:
                self.entry.setText(selected)

        def get_path(self):
            return self.entry.text().strip()

    class TextInput(QWidget):
        def __init__(self, label_text, initial_value=""):
            super().__init__()
            self.setFixedHeight(30)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.setSpacing(4)

            label = QLabel(label_text.lower())
            label.setFixedWidth(130)
            self.entry = QLineEdit(initial_value)
            self.entry.setMinimumWidth(320)
            self.entry.setFixedHeight(26)
            self.entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(label)
            layout.addWidget(self.entry, 1)

        def get_value(self):
            return self.entry.text().strip()

    class CategorySection(QGroupBox):
        def __init__(self, title):
            super().__init__()
            self.setTitle(title)
            self.content_layout = QVBoxLayout(self)
            self.content_layout.setContentsMargins(8, 8, 8, 8)
            self.content_layout.setSpacing(3)

        def add_widget(self, widget):
            self.content_layout.addWidget(widget)

        def add_layout(self, layout):
            self.content_layout.addLayout(layout)

    class Cs2PluginUpdater(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(APP_TITLE)
            self.setMinimumWidth(860)
            self.setMinimumHeight(520)

            self.settings = load_settings()
            self.selectors = {}
            self.autojoiner_stop_event = threading.Event()
            self.autojoiner_thread = None
            self.log_bridge = LogBridge()
            self.log_bridge.message.connect(self.log)
            self.log_bridge.autojoiner_stopped.connect(self.on_autojoiner_stopped)
            self._build_ui()

        def _build_ui(self):
            central = QWidget()
            self.setCentralWidget(central)

            outer = QVBoxLayout(central)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(4)

            self.load_cs2fixes_checkbox = QCheckBox("launch with cs2fixes")
            self.load_cs2fixes_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "launch_with_cs2fixes", False)
            )
            self.load_cs2fixes_checkbox.stateChanged.connect(self.update_autojoiner_state)

            self.launch_workshop_checkbox = QCheckBox("launch workshop tools")
            self.launch_workshop_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "launch_workshop", False)
            )
            self.launch_workshop_checkbox.stateChanged.connect(self.update_autojoiner_state)

            top_actions_widget = QWidget()
            top_actions_widget.setFixedHeight(34)
            top_actions_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            top_actions = QHBoxLayout(top_actions_widget)
            top_actions.setContentsMargins(0, 2, 0, 2)
            top_actions.setSpacing(10)
            top_actions.addWidget(self.load_cs2fixes_checkbox)
            top_actions.addWidget(self.launch_workshop_checkbox)
            top_actions.addStretch(1)

            launch_button = QPushButton("Launch CS2")
            launch_button.setMinimumWidth(110)
            launch_button.setFixedHeight(26)
            launch_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            launch_button.clicked.connect(self.launch_game)
            top_actions.addWidget(launch_button)
            outer.addWidget(top_actions_widget)

            cs2fixes_section = CategorySection("cs2fixes")
            self.cs2_root_selector = PathSelector(
                "cs2 root directory",
                get_setting(self.settings, "fields", "cs2_root", find_cs2_root()),
                mode="directory",
                detect_callback=find_cs2_root,
            )
            cs2fixes_section.add_widget(self.cs2_root_selector)

            self.steamid64_input = TextInput(
                "admin steamID64",
                get_setting(self.settings, "fields", "steamid64", ""),
            )
            cs2fixes_section.add_widget(self.steamid64_input)

            self.cs2fixes_cfg_selector = PathSelector(
                "cs2fixes.cfg",
                get_setting(self.settings, "fields", "cs2fixes_cfg", find_default_cs2fixes_cfg()),
                file_filter="Config files (*.cfg);;All files (*.*)",
                link_url=CS2FIXES_LINKS["cs2fixes.cfg"],
            )
            cs2fixes_section.add_widget(self.cs2fixes_cfg_selector)

            defaults = find_default_zips()
            for label, default_key in ZIP_FIELDS:
                selector = PathSelector(
                    label,
                    get_setting(self.settings, "fields", zip_setting_key(label), defaults.get(default_key, "")),
                    file_filter="Zip files (*.zip)",
                    link_url=CS2FIXES_LINKS.get(label),
                )
                cs2fixes_section.add_widget(selector)
                self.selectors[label] = selector

            install_layout = QHBoxLayout()
            install_layout.setContentsMargins(0, 2, 0, 2)
            install_button = QPushButton("Install")
            install_button.setMinimumWidth(90)
            install_button.setFixedHeight(26)
            install_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            install_button.clicked.connect(self.install_all)
            install_layout.addWidget(install_button)
            install_layout.addStretch(1)
            cs2fixes_section.add_layout(install_layout)
            cs2fixes_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cs2fixes_section.setMinimumHeight(cs2fixes_section.sizeHint().height())
            outer.addWidget(cs2fixes_section)

            autojoiner_section = CategorySection("autojoiner")
            autojoiner_layout = QGridLayout()
            autojoiner_layout.setContentsMargins(0, 2, 0, 2)
            autojoiner_layout.setHorizontalSpacing(6)
            autojoiner_layout.setVerticalSpacing(0)
            self.autojoiner_checkbox = QCheckBox("autojoiner")
            self.autojoiner_checkbox.setChecked(get_bool_setting(self.settings, "checkboxes", "autojoiner", False))
            self.autojoiner_checkbox.stateChanged.connect(self.update_autojoiner_state)
            autojoiner_layout.addWidget(self.autojoiner_checkbox, 0, 0)
            autojoiner_layout.addWidget(QLabel("ip"), 0, 1)
            self.autojoiner_ip_entry = QLineEdit(get_setting(self.settings, "fields", "autojoiner_ip", ""))
            self.autojoiner_ip_entry.setMinimumWidth(220)
            self.autojoiner_ip_entry.setFixedHeight(26)
            self.autojoiner_ip_entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            autojoiner_layout.addWidget(self.autojoiner_ip_entry, 0, 2)
            autojoiner_layout.addWidget(QLabel("port"), 0, 3)
            self.autojoiner_port_entry = QLineEdit(get_setting(self.settings, "fields", "autojoiner_port", ""))
            self.autojoiner_port_entry.setFixedWidth(80)
            self.autojoiner_port_entry.setFixedHeight(26)
            self.autojoiner_port_entry.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            autojoiner_layout.addWidget(self.autojoiner_port_entry, 0, 4)
            autojoiner_layout.addWidget(QLabel("name"), 0, 5)
            self.autojoiner_name_entry = QLineEdit(get_setting(self.settings, "fields", "autojoiner_name", ""))
            self.autojoiner_name_entry.setMinimumWidth(150)
            self.autojoiner_name_entry.setFixedHeight(26)
            self.autojoiner_name_entry.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            autojoiner_layout.addWidget(self.autojoiner_name_entry, 0, 6)
            self.autojoiner_toggle_button = QPushButton("Start")
            self.autojoiner_toggle_button.setMinimumWidth(70)
            self.autojoiner_toggle_button.setFixedHeight(26)
            self.autojoiner_toggle_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.autojoiner_toggle_button.clicked.connect(self.toggle_autojoiner)
            autojoiner_layout.addWidget(self.autojoiner_toggle_button, 0, 7)
            autojoiner_layout.setColumnStretch(2, 1)
            autojoiner_section.add_layout(autojoiner_layout)
            autojoiner_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            autojoiner_section.setMinimumHeight(autojoiner_section.sizeHint().height())
            outer.addWidget(autojoiner_section)

            outer.addWidget(QLabel("console"))
            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.document().setMaximumBlockCount(CONSOLE_MAX_LINES)
            self.log_text.setMinimumHeight(90)
            self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            outer.addWidget(self.log_text, 1)
            self.update_autojoiner_state()
            self.setMinimumHeight(max(self.minimumHeight(), self.sizeHint().height()))

        def clear_log(self):
            self.log_text.clear()

        def log(self, message, color=None):
            if color is None and str(message).startswith("ERROR:"):
                color = "#ff5c5c"

            if color:
                self.log_text.append(f'<span style="color: {color};">{html.escape(str(message))}</span>')
            else:
                self.log_text.append(str(message))
            QApplication.processEvents()

        def fail(self, title, message):
            self.log(f"ERROR: {message}")
            QMessageBox.critical(self, title, message)

        def update_autojoiner_state(self):
            launch_option_enabled = self.load_cs2fixes_checkbox.isChecked() or self.launch_workshop_checkbox.isChecked()
            autojoiner_running = self.is_autojoiner_running()

            if launch_option_enabled:
                if autojoiner_running:
                    self.autojoiner_stop_event.set()
                self.autojoiner_checkbox.setChecked(False)
                self.autojoiner_checkbox.setEnabled(False)
            else:
                self.autojoiner_checkbox.setEnabled(True)

            field_enabled = not launch_option_enabled and not autojoiner_running
            self.autojoiner_ip_entry.setEnabled(field_enabled)
            self.autojoiner_port_entry.setEnabled(field_enabled)
            self.autojoiner_name_entry.setEnabled(field_enabled)
            self.autojoiner_toggle_button.setEnabled(not launch_option_enabled)
            self.autojoiner_toggle_button.setText("Stop" if autojoiner_running else "Start")

        def closeEvent(self, event):
            self.autojoiner_stop_event.set()
            save_settings(
                self.cs2_root_selector.get_path(),
                self.steamid64_input.get_value(),
                self.cs2fixes_cfg_selector.get_path(),
                self.autojoiner_ip_entry.text().strip(),
                self.autojoiner_port_entry.text().strip(),
                self.autojoiner_name_entry.text().strip(),
                self.selectors,
                self.load_cs2fixes_checkbox.isChecked(),
                self.launch_workshop_checkbox.isChecked(),
                self.autojoiner_checkbox.isChecked(),
            )
            event.accept()

        def install_all(self):
            self.clear_log()
            started_at = time.perf_counter()
            self.log("Starting install.")

            cs2_root = Path(self.cs2_root_selector.get_path())
            if not cs2_root.is_dir():
                self.fail("Invalid CS2 root", "Select a valid CS2 root directory first.")
                return

            self.log(f"CS2 root: {cs2_root}")

            steamid64 = self.steamid64_input.get_value()
            if not steamid64:
                self.fail("Missing steamID64", "Enter a steamID64 value first.")
                return

            self.log("steamID64 value found.")

            selected_cs2fixes_cfg = Path(self.cs2fixes_cfg_selector.get_path())
            if not selected_cs2fixes_cfg.is_file():
                self.fail("Invalid cs2fixes.cfg", "Select a valid cs2fixes.cfg file first.")
                return

            self.log(f"cs2fixes.cfg source: {selected_cs2fixes_cfg}")

            results = []
            for selector_name, display_name, target_path, source_prefix, exclude_prefixes in CSGO_INSTALLS:
                target_dir = cs2_root / target_path
                zip_path = Path(self.selectors[selector_name].get_path())

                self.log(f"Preparing {display_name}.")
                self.log(f"Target: {target_dir}")

                if not target_dir.is_dir():
                    try:
                        self.log(f"Creating target directory: {target_dir}")
                        target_dir.mkdir(parents=True, exist_ok=True)
                    except OSError as error:
                        self.fail(
                            "Invalid CS2 install",
                            f"Could not create the target directory for {display_name}:\n{target_dir}\n\n{error}",
                        )
                        return

                if not zip_path.is_file() or zip_path.suffix.lower() != ".zip":
                    self.fail(
                        f"Invalid {display_name} zip",
                        f"Select a valid {display_name} .zip file first.",
                    )
                    return

                self.log(f"Extracting from: {zip_path}")
                if source_prefix:
                    self.log(f"Zip folder filter: {source_prefix}")

                try:
                    self.log(f"Verifying zip contents for {display_name}.")
                    validate_zip_contents(zip_path, display_name)
                    extracted_count = extract_zip_overwrite(
                        zip_path,
                        target_dir,
                        source_prefix,
                        exclude_prefixes,
                    )
                except zipfile.BadZipFile:
                    self.fail(
                        f"Invalid {display_name} zip",
                        f"The selected {display_name} file is not a valid zip.",
                    )
                    return
                except OSError as error:
                    self.fail("Install failed", f"Could not extract {display_name}:\n{error}")
                    return
                except ValueError as error:
                    self.fail("Install blocked", str(error))
                    return

                if source_prefix and extracted_count == 0:
                    self.fail(
                        "Install failed",
                        f"No files were found under {source_prefix} in the {display_name} zip.",
                    )
                    return

                self.log(f"Finished {display_name}: {extracted_count} files.")
                results.append(f"{display_name}: {extracted_count} files to {target_path}")

            admins_path = cs2_root / "game" / "csgo" / "addons" / "cs2fixes" / "configs" / "admins.jsonc"
            try:
                self.log(f"Writing admins.jsonc: {admins_path}")
                update_admins_steamid64(admins_path, steamid64)
            except FileNotFoundError:
                self.fail("Install failed", f"Could not find admins.jsonc:\n{admins_path}")
                return
            except ValueError as error:
                self.fail("Install failed", str(error))
                return
            except OSError as error:
                self.fail("Install failed", f"Could not update admins.jsonc:\n{error}")
                return

            self.log("Finished admins.jsonc.")
            results.append("admins.jsonc: steamID64 updated")

            cs2fixes_cfg_path = cs2_root / "game" / "csgo" / "cfg" / "cs2fixes" / "cs2fixes.cfg"
            try:
                self.log(f"Copying cs2fixes.cfg to: {cs2fixes_cfg_path}")
                write_cs2fixes_cfg(cs2fixes_cfg_path, selected_cs2fixes_cfg)
            except OSError as error:
                self.fail("Install failed", f"Could not update cs2fixes.cfg:\n{error}")
                return

            self.log("Finished cs2fixes.cfg.")
            results.append("cs2fixes.cfg: updated")
            elapsed_seconds = time.perf_counter() - started_at
            self.log(f"Install complete in {elapsed_seconds:.2f} seconds.", "#36d675")

        def launch_game(self):
            self.clear_log()
            self.log("Preparing launch.")

            cs2_root = Path(self.cs2_root_selector.get_path())
            if not cs2_root.is_dir():
                self.fail("Invalid CS2 root", "Select a valid CS2 root directory first.")
                return

            try:
                launch_game_with_options(
                    cs2_root,
                    self.load_cs2fixes_checkbox.isChecked(),
                    self.launch_workshop_checkbox.isChecked(),
                    self.log,
                )
            except FileNotFoundError as error:
                self.fail("Launch failed", f"Could not find required file:\n{missing_file_text(error)}")
                return
            except OSError as error:
                self.fail("Launch failed", str(error))
                return

            if self.autojoiner_checkbox.isChecked():
                self.start_autojoiner()

        def toggle_autojoiner(self):
            if self.is_autojoiner_running():
                self.stop_autojoiner()
            else:
                self.start_autojoiner()

        def start_autojoiner(self):
            server_ip = self.autojoiner_ip_entry.text().strip()
            server_port = self.autojoiner_port_entry.text().strip()
            player_name = self.autojoiner_name_entry.text().strip()

            if not server_ip:
                self.fail("Autojoiner failed", "Enter an autojoiner server IP first.")
                return

            if not server_port.isdigit():
                self.fail("Autojoiner failed", "Enter a numeric autojoiner server port first.")
                return

            if not player_name:
                self.fail("Autojoiner failed", "Enter a player name to check for first.")
                return

            if self.autojoiner_thread and self.autojoiner_thread.is_alive():
                self.log("Autojoiner is already running.")
                return

            self.autojoiner_stop_event.clear()
            self.log(f"Starting autojoiner for {server_ip}:{server_port}.")
            self.autojoiner_thread = threading.Thread(
                target=self.run_autojoiner_thread,
                args=(
                    server_ip,
                    int(server_port),
                    player_name,
                    AUTOJOINER_PLAYER_LIMIT,
                    AUTOJOINER_INTERVAL_SECONDS,
                    self.autojoiner_stop_event,
                    self.thread_log,
                ),
                daemon=True,
            )
            self.autojoiner_thread.start()
            self.update_autojoiner_state()

        def stop_autojoiner(self):
            if not self.is_autojoiner_running():
                self.update_autojoiner_state()
                return

            self.log("Stopping autojoiner.")
            self.autojoiner_stop_event.set()
            self.update_autojoiner_state()

        def run_autojoiner_thread(
            self,
            server_ip,
            server_port,
            player_name,
            player_limit,
            interval_seconds,
            stop_event,
            log,
        ):
            try:
                run_autojoiner(
                    server_ip,
                    server_port,
                    player_name,
                    player_limit,
                    interval_seconds,
                    stop_event,
                    log,
                )
            finally:
                self.log_bridge.autojoiner_stopped.emit()

        def on_autojoiner_stopped(self):
            self.autojoiner_thread = None
            self.update_autojoiner_state()

        def is_autojoiner_running(self):
            return self.autojoiner_thread is not None and self.autojoiner_thread.is_alive()

        def thread_log(self, message):
            self.log_bridge.message.emit(message)

    app = QApplication(sys.argv)
    window = Cs2PluginUpdater()
    window.show()
    return app.exec()


def find_default_zips():
    required_files = Path(__file__).resolve().parent / "required files"
    defaults = {}

    if not required_files.is_dir():
        return defaults

    zip_files = list(required_files.glob("*.zip"))
    for key in [default_key for _, default_key in ZIP_FIELDS]:
        match = next((path for path in zip_files if key.lower() in path.name.lower()), None)
        if match:
            defaults[key] = str(match)

    return defaults


def load_settings():
    settings = configparser.ConfigParser()
    if SETTINGS_FILE.is_file():
        settings.read(SETTINGS_FILE, encoding="utf-8")

    return settings


def save_settings(
    cs2_root,
    steamid64,
    cs2fixes_cfg,
    autojoiner_ip,
    autojoiner_port,
    autojoiner_name,
    selectors,
    launch_with_cs2fixes,
    launch_workshop,
    autojoiner,
):
    settings = configparser.ConfigParser()
    settings["fields"] = {
        "cs2_root": cs2_root,
        "steamid64": steamid64,
        "cs2fixes_cfg": cs2fixes_cfg,
        "autojoiner_ip": autojoiner_ip,
        "autojoiner_port": autojoiner_port,
        "autojoiner_name": autojoiner_name,
    }

    for label, selector in selectors.items():
        settings["fields"][zip_setting_key(label)] = selector.get_path()

    settings["checkboxes"] = {
        "launch_with_cs2fixes": str(bool(launch_with_cs2fixes)),
        "launch_workshop": str(bool(launch_workshop)),
        "autojoiner": str(bool(autojoiner)),
    }

    with SETTINGS_FILE.open("w", encoding="utf-8") as settings_file:
        settings.write(settings_file)


def get_setting(settings, section, option, fallback):
    if settings.has_option(section, option):
        return settings.get(section, option)

    return fallback


def get_bool_setting(settings, section, option, fallback):
    if settings.has_option(section, option):
        return settings.getboolean(section, option)

    return fallback


def zip_setting_key(label):
    return "zip_" + label.replace(" ", "_")


def find_default_cs2fixes_cfg():
    template_path = Path(__file__).resolve().parent / "cs2fixes_template.cfg"
    if template_path.is_file():
        return str(template_path)

    return ""


def validate_zip_contents(zip_path, display_name):
    required_file = ZIP_REQUIRED_FILES.get(display_name)

    if not required_file and display_name != "metamod launcher":
        return

    with zipfile.ZipFile(zip_path) as archive:
        member_names = [
            normalize_zip_path(member.filename)
            for member in archive.infolist()
            if not member.is_dir()
        ]

    if display_name == "metamod launcher":
        if any(Path(member_name).name.casefold() == "metamod-launcher.exe" for member_name in member_names):
            return
        raise ValueError("metamod launcher zip must contain metamod-launcher.exe.")

    required_file_normalized = normalize_zip_path(required_file).casefold()
    if any(member_name.casefold() == required_file_normalized for member_name in member_names):
        return

    raise ValueError(f"{display_name} zip must contain {required_file}.")


def extract_zip_overwrite(zip_path, target_dir, source_prefix=None, exclude_prefixes=None):
    target_root = target_dir.resolve()
    extracted_count = 0
    normalized_prefix = normalize_zip_path(source_prefix) if source_prefix else None
    normalized_prefix_lower = normalized_prefix.lower() if normalized_prefix else None
    normalized_excludes = [
        normalize_zip_path(prefix).lower()
        for prefix in (exclude_prefixes or [])
    ]

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_name = normalize_zip_path(member.filename)
            relative_name = member_name

            if any(member_name.lower().startswith(prefix) for prefix in normalized_excludes):
                continue

            if normalized_prefix:
                if not member_name.lower().startswith(normalized_prefix_lower):
                    continue
                relative_name = member_name[len(normalized_prefix) :]

                if not relative_name:
                    continue

            destination = (target_root / relative_name).resolve()

            if not is_relative_to(destination, target_root):
                raise ValueError(f"Zip entry would extract outside the target directory: {member.filename}")

            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                output.write(source.read())
            extracted_count += 1

    return extracted_count


def update_admins_steamid64(admins_path, steamid64):
    admins_path.parent.mkdir(parents=True, exist_ok=True)
    admins_path.write_text(ADMINS_TEMPLATE.replace("<id here>", steamid64), encoding="utf-8")


def write_cs2fixes_cfg(config_path, source_path):
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, config_path)


def update_gameinfo_workshop_filters(cs2_root, launch_workshop, log):
    gameinfo_path = cs2_root / "game" / "csgo_core" / "gameinfo.gi"
    backup_path = gameinfo_path.with_name(GAMEINFO_WORKSHOP_BACKUP)

    log(f"Checking gameinfo.gi: {gameinfo_path}")
    if not gameinfo_path.is_file():
        raise FileNotFoundError(gameinfo_path)

    content = gameinfo_path.read_text(encoding="utf-8-sig")
    lines = content.splitlines(keepends=True)

    if launch_workshop:
        log("Removing workshop model filter lines from gameinfo.gi.")
        updated_lines, removed_lines, insert_index = remove_gameinfo_workshop_lines(lines)
        if not removed_lines:
            log("Workshop model filters already removed from gameinfo.gi.")
            return

        backup_path.write_text(
            json.dumps({"index": insert_index, "lines": removed_lines}, indent=2),
            encoding="utf-8",
        )
        gameinfo_path.write_text("".join(updated_lines), encoding="utf-8")
        log(f"Removed workshop model filters from: {gameinfo_path}")
        return

    if has_all_gameinfo_workshop_lines(lines):
        log("Workshop model filters already restored in gameinfo.gi.")
        return

    log("Restoring workshop model filter lines to gameinfo.gi.")
    backup = load_gameinfo_workshop_backup(backup_path)
    if backup:
        restore_index = min(backup["index"], len(lines))
        restore_lines = backup["lines"]
    else:
        restore_index = find_gameinfo_substr_insert_index(lines)
        newline = detect_newline(content)
        prefix = detect_gameinfo_substr_indent(lines)
        restore_lines = [f"{prefix}{line}{newline}" for line in GAMEINFO_WORKSHOP_FILTER_LINES]

    cleaned_lines, _, _ = remove_gameinfo_workshop_lines(lines)
    restore_index = min(restore_index, len(cleaned_lines))
    cleaned_lines[restore_index:restore_index] = restore_lines
    gameinfo_path.write_text("".join(cleaned_lines), encoding="utf-8")
    log(f"Restored workshop model filters in: {gameinfo_path}")


def remove_gameinfo_workshop_lines(lines):
    filter_line_set = {line.casefold() for line in GAMEINFO_WORKSHOP_FILTER_LINES}
    updated_lines = []
    removed_lines = []
    insert_index = None

    for line in lines:
        if line.strip().casefold() in filter_line_set:
            if insert_index is None:
                insert_index = len(updated_lines)
            removed_lines.append(line)
            continue
        updated_lines.append(line)

    return updated_lines, removed_lines, insert_index


def has_all_gameinfo_workshop_lines(lines):
    existing_lines = {line.strip().casefold() for line in lines}
    return all(line.casefold() in existing_lines for line in GAMEINFO_WORKSHOP_FILTER_LINES)


def load_gameinfo_workshop_backup(backup_path):
    if not backup_path.is_file():
        return None

    try:
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(backup, dict):
        return None
    if not isinstance(backup.get("index"), int):
        return None
    if not isinstance(backup.get("lines"), list):
        return None
    if not all(isinstance(line, str) for line in backup["lines"]):
        return None

    return backup


def detect_newline(content):
    if "\r\n" in content:
        return "\r\n"
    if "\r" in content:
        return "\r"
    return "\n"


def find_gameinfo_substr_insert_index(lines):
    for index, line in enumerate(lines):
        if line.strip().casefold().startswith('"substr" '):
            return index

    return len(lines)


def detect_gameinfo_substr_indent(lines):
    for line in lines:
        stripped = line.lstrip(" \t")
        if stripped.casefold().startswith('"substr" '):
            return line[: len(line) - len(stripped)]

    return ""


def launch_game_with_options(cs2_root, launch_with_cs2fixes, launch_workshop, log):
    bin_dir = cs2_root / "game" / "bin" / "win64"
    server_dll = bin_dir / "server.dll"
    workshop_args = ["-disable_workshop_command_filtering", "-insecure"]

    update_gameinfo_workshop_filters(cs2_root, launch_workshop, log)

    if not launch_with_cs2fixes:
        log(f"Deleting if present: {server_dll}")
        delete_file_if_exists(server_dll)

    if launch_with_cs2fixes and not launch_workshop:
        launcher_path = bin_dir / "metamod-launcher.exe"
        log(f"Launching: {launcher_path}")
        launch_executable(launcher_path)
        log("metamod-launcher.exe launched.")
        return

    if launch_with_cs2fixes and launch_workshop:
        launcher_path = bin_dir / "csgocfg.exe"
        log("Copying Metamod binaries to tools directory.")
        copied_files = copy_metamod_to_tools(cs2_root)
        for copied_file in copied_files:
            log(f"Copied: {copied_file}")
        log(f"Launching: {launcher_path} {' '.join(workshop_args)}")
        launch_executable(launcher_path, workshop_args)
        log("csgocfg.exe launched.")
        return

    if not launch_with_cs2fixes and not launch_workshop:
        steam_uri = "steam://rungameid/730"
        log(f"Opening: {steam_uri}")
        launch_uri(steam_uri)
        log("Steam CS2 launch URI opened.")
        return

    launcher_path = bin_dir / "csgocfg.exe"
    log(f"Launching: {launcher_path} {' '.join(workshop_args)}")
    launch_executable(launcher_path, workshop_args)
    log("csgocfg.exe launched.")


def run_autojoiner(server_ip, server_port, player_name, player_limit, interval_seconds, stop_event, log):
    try:
        import a2s
    except ImportError:
        log("ERROR: Python package 'a2s' is not installed.")
        return

    server_addr = (server_ip, server_port)
    connect_uri = f"steam://run/730//+connect {server_ip}:{server_port}"
    connect_attempted = False
    player_check_until = None

    while not stop_event.is_set():
        try:
            if connect_attempted:
                log(f"checking for '{player_name}'")

            players = a2s.players(server_addr, timeout=3.0)
            if any(name_matches(player.name, player_name) for player in players):
                log(f"Detected player '{player_name}' in server; stopping autojoiner.")
                play_success_sound()
                return

            if connect_attempted and time.monotonic() >= player_check_until:
                connect_attempted = False
                player_check_until = None

            info = a2s.info(server_addr, timeout=3.0)
            current_players = info.player_count
            max_players = info.max_players
            map_name = info.map_name
            log(f"[{system_time()}] {map_name} - player count: {current_players}/{max_players}")

            if current_players < player_limit and not connect_attempted:
                launch_uri(connect_uri)
                play_join_attempt_sound()
                connect_attempted = True
                player_check_until = time.monotonic() + AUTOJOINER_CONNECT_ATTEMPT_SECONDS
        except Exception as error:
            log(f"Server query failed: {error}")

        stop_event.wait(interval_seconds)

    log("Autojoiner stopped.")


def name_matches(server_name, expected_name):
    return server_name.casefold() == expected_name.casefold()


def system_time():
    return datetime.now().strftime("%H:%M:%S")


def play_join_attempt_sound():
    play_beeps([(600, 200), (600, 200)])


def play_success_sound():
    play_beeps([(600, 200), (800, 200), (1000, 300)])


def play_beeps(beeps):
    try:
        if sys.platform == "win32":
            import winsound
            for frequency, duration in beeps:
                winsound.Beep(frequency, duration)
        else:
            print("\a")
    except Exception:
        pass


def copy_metamod_to_tools(cs2_root):
    source_dir = cs2_root / "game" / "csgo" / "addons" / "metamod" / "bin" / "win64"
    target_dir = cs2_root / "game" / "bin" / "win64"
    file_names = ["server.dll", "metamod.2.cs2.dll"]
    copied_files = []

    if not target_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)

    for file_name in file_names:
        source_file = source_dir / file_name
        target_file = target_dir / file_name

        if not source_file.is_file():
            raise FileNotFoundError(source_file)

        shutil.copyfile(source_file, target_file)
        copied_files.append(target_file)

    return copied_files


def launch_executable(executable_path, args=None):
    if not executable_path.is_file():
        raise FileNotFoundError(executable_path)

    subprocess.Popen([str(executable_path), *(args or [])], cwd=str(executable_path.parent))


def launch_uri(uri):
    if not webbrowser.open(uri):
        raise OSError(f"Could not open URI: {uri}")


def delete_file_if_exists(path):
    if path.exists():
        path.unlink()


def normalize_zip_path(path):
    return path.replace("\\", "/").lstrip("/")


def is_relative_to(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def find_cs2_root():
    candidates = []

    for steam_root in find_steam_roots():
        candidates.append(steam_root / "steamapps" / "common" / CS2_FOLDER_NAME)

    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidates.extend(
            [
                Path(f"{drive}:/SteamLibrary/steamapps/common/{CS2_FOLDER_NAME}"),
                Path(f"{drive}:/Program Files (x86)/Steam/steamapps/common/{CS2_FOLDER_NAME}"),
                Path(f"{drive}:/Program Files/Steam/steamapps/common/{CS2_FOLDER_NAME}"),
            ]
        )

    for candidate in candidates:
        if candidate.is_dir():
            return str(candidate)

    return ""


def find_steam_roots():
    roots = []
    steam_install = find_steam_install_path()

    if steam_install:
        roots.append(steam_install)
        library_file = steam_install / "steamapps" / "libraryfolders.vdf"
        roots.extend(read_steam_library_paths(library_file))

    return dedupe_paths(roots)


def find_steam_install_path():
    try:
        import winreg
    except ImportError:
        return None

    registry_locations = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
    ]

    for root_key, subkey in registry_locations:
        try:
            with winreg.OpenKey(root_key, subkey) as key:
                install_path, _ = winreg.QueryValueEx(key, "SteamPath")
                return Path(install_path)
        except OSError:
            continue

    return None


def read_steam_library_paths(library_file):
    if not library_file.is_file():
        return []

    try:
        text = library_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    paths = []
    for match in re.finditer(r'"path"\s+"([^"]+)"', text):
        paths.append(Path(match.group(1).replace("\\\\", "\\")))

    return paths


def dedupe_paths(paths):
    deduped = []
    seen = set()

    for path in paths:
        normalized = str(path).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(path)

    return deduped


def missing_file_text(error):
    return str(error.filename or error)


def run_cli(args):
    settings = load_settings()
    cs2_root = Path(get_setting(settings, "fields", "cs2_root", find_cs2_root()))

    if not cs2_root.is_dir():
        print("Could not find a valid CS2 root directory. Open the GUI with -gui and select it.", file=sys.stderr)
        return 1

    try:
        launch_game_with_options(cs2_root, args.cs2fixes, args.tools, print)
    except FileNotFoundError as error:
        print(f"Launch failed. Could not find required file: {missing_file_text(error)}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Launch failed. {error}", file=sys.stderr)
        return 1

    if args.autojoiner:
        stop_event = threading.Event()
        try:
            run_autojoiner(
                args.ip,
                args.port,
                args.name,
                AUTOJOINER_PLAYER_LIMIT,
                AUTOJOINER_INTERVAL_SECONDS,
                stop_event,
                print,
            )
        except KeyboardInterrupt:
            stop_event.set()
            print("Autojoiner stopped.")
            return 130

    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("-gui", action="store_true", help="launch gui")
    parser.add_argument("-tools", action="store_true", help="launch workshop tools")
    parser.add_argument("-cs2fixes", action="store_true", help="launch with cs2fixes")
    parser.add_argument("-autojoiner", action="store_true", help="run autojoiner")
    parser.add_argument("-ip", help="autojoiner server IP")
    parser.add_argument("-port", type=int, help="autojoiner server port")
    parser.add_argument("-name", help="autojoiner player name to check for")
    args = parser.parse_args(argv)

    autojoiner_flag_present = (
        args.autojoiner
        or args.ip is not None
        or args.port is not None
        or args.name is not None
    )
    if autojoiner_flag_present and (args.tools or args.cs2fixes):
        parser.error("autojoiner flags cannot be combined with -tools or -cs2fixes")

    if args.autojoiner:
        missing = [
            flag
            for flag, value in (("-ip", args.ip), ("-port", args.port), ("-name", args.name))
            if value is None or value == ""
        ]
        if missing:
            parser.error(f"-autojoiner requires {' '.join(missing)}")

    return args


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.gui:
        return launch_gui()

    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
