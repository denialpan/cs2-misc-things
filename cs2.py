from pathlib import Path
import argparse
import configparser
from datetime import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import zipfile


APP_TITLE = "CS2 Launcher"
SETTINGS_FILE = Path(__file__).resolve().parent / "settings.ini"
AUTOJOINER_INTERVAL_SECONDS = 1.5
AUTOJOINER_PLAYER_LIMIT = 62
AUTOJOINER_CONNECT_ATTEMPT_SECONDS = 10
A2S_TIMEOUT_SECONDS = 3.0
CONSOLE_MAX_LINES = 1000
MIN_WINDOW_HEIGHT = 50
BUILT_IN_COMPILER_PRESETS = ("full compile", "fast compile", "final compile", "only entities")
ANSI_RESET = "\033[0m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"
ANSI_WHITE = "\033[37m"
ANSI_GRAY = "\033[90m"

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
        from PySide6.QtCore import QObject, Qt, QTimer, Signal
        from PySide6.QtGui import QTextCursor
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSizePolicy,
            QTabWidget,
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
        raw_text = Signal(str)
        autojoiner_stopped = Signal()
        compiler_finished = Signal(int, float)

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
                QMessageBox.information(self, "Path detected", f"Found path:\n{detected_path}")
            else:
                QMessageBox.critical(self, "Path not found", "Could not automatically locate the path.")

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

    class Cs2PluginUpdater(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(APP_TITLE)
            self.setMinimumWidth(860)
            self.setMinimumHeight(MIN_WINDOW_HEIGHT)

            self.settings = load_settings()
            self.selectors = {}
            self.custom_compiler_presets = load_custom_compiler_presets(self.settings)
            self.applying_compiler_preset = False
            self.compiler_output_buffer = ""
            self.autojoiner_stop_event = threading.Event()
            self.autojoiner_thread = None
            self.log_bridge = LogBridge()
            self.log_bridge.message.connect(self.log)
            self.log_bridge.raw_text.connect(self.append_log_text)
            self.log_bridge.autojoiner_stopped.connect(self.on_autojoiner_stopped)
            self.log_bridge.compiler_finished.connect(self.on_resourcecompiler_finished)
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

            tabs = QTabWidget()
            self.tabs = tabs
            tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            tabs.currentChanged.connect(self.resize_for_current_tab)

            cs2fixes_section = QWidget()
            cs2fixes_layout = QVBoxLayout(cs2fixes_section)
            cs2fixes_layout.setContentsMargins(8, 8, 8, 8)
            cs2fixes_layout.setSpacing(3)
            self.cs2_root_selector = PathSelector(
                "cs2 root directory",
                get_setting(self.settings, "fields", "cs2_root", find_cs2_root()),
                mode="directory",
                detect_callback=find_cs2_root,
            )
            cs2fixes_layout.addWidget(self.cs2_root_selector)

            self.steamid64_input = TextInput(
                "admin steamID64",
                get_setting(self.settings, "fields", "steamid64", ""),
            )
            cs2fixes_layout.addWidget(self.steamid64_input)

            self.cs2fixes_cfg_selector = PathSelector(
                "cs2fixes.cfg",
                get_setting(self.settings, "fields", "cs2fixes_cfg", find_default_cs2fixes_cfg()),
                file_filter="Config files (*.cfg);;All files (*.*)",
                link_url=CS2FIXES_LINKS["cs2fixes.cfg"],
            )
            cs2fixes_layout.addWidget(self.cs2fixes_cfg_selector)

            defaults = find_default_zips()
            for label, default_key in ZIP_FIELDS:
                selector = PathSelector(
                    label,
                    get_setting(self.settings, "fields", zip_setting_key(label), defaults.get(default_key, "")),
                    file_filter="Zip files (*.zip)",
                    link_url=CS2FIXES_LINKS.get(label),
                )
                cs2fixes_layout.addWidget(selector)
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
            cs2fixes_layout.addLayout(install_layout)
            cs2fixes_layout.addStretch(1)
            tabs.addTab(cs2fixes_section, "cs2fixes")

            map_compiler_section = QWidget()
            map_compiler_layout = QVBoxLayout(map_compiler_section)
            map_compiler_layout.setContentsMargins(8, 8, 8, 8)
            map_compiler_layout.setSpacing(6)

            preset_layout = QHBoxLayout()
            preset_layout.setContentsMargins(0, 2, 0, 2)
            preset_layout.setSpacing(6)
            preset_layout.addWidget(QLabel("preset"))
            self.compiler_preset_combo = QComboBox()
            self.compiler_preset_combo.addItems(
                ["custom", "full compile", "fast compile", "final compile", "only entities"]
                + sorted(self.custom_compiler_presets)
            )
            self.compiler_preset_combo.setCurrentText("custom")
            self.compiler_preset_combo.setFixedHeight(26)
            self.compiler_preset_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.compiler_preset_combo.currentTextChanged.connect(self.apply_compiler_preset)
            preset_layout.addWidget(self.compiler_preset_combo)
            self.save_compiler_preset_button = QPushButton("Save Preset")
            self.save_compiler_preset_button.setMinimumWidth(92)
            self.save_compiler_preset_button.setFixedHeight(26)
            self.save_compiler_preset_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.save_compiler_preset_button.clicked.connect(self.save_custom_compiler_preset)
            preset_layout.addWidget(self.save_compiler_preset_button)
            self.delete_compiler_preset_button = QPushButton("Delete Preset")
            self.delete_compiler_preset_button.setMinimumWidth(96)
            self.delete_compiler_preset_button.setFixedHeight(26)
            self.delete_compiler_preset_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.delete_compiler_preset_button.clicked.connect(self.delete_custom_compiler_preset)
            preset_layout.addWidget(self.delete_compiler_preset_button)
            preset_layout.addStretch(1)
            map_compiler_layout.addLayout(preset_layout)

            self.resourcecompiler_selector = PathSelector(
                "resourcecompiler.exe",
                get_setting(
                    self.settings,
                    "fields",
                    "resourcecompiler",
                    find_resourcecompiler_path(Path(self.cs2_root_selector.get_path())),
                ),
                file_filter="Executable files (*.exe);;All files (*.*)",
                detect_callback=self.detect_resourcecompiler_path,
            )
            map_compiler_layout.addWidget(self.resourcecompiler_selector)

            compiler_groups = QGridLayout()
            compiler_groups.setContentsMargins(0, 0, 0, 0)
            compiler_groups.setHorizontalSpacing(8)
            compiler_groups.setVerticalSpacing(6)

            world_group = QGroupBox("world")
            world_layout = QVBoxLayout(world_group)
            world_layout.setContentsMargins(8, 8, 8, 8)
            world_layout.setSpacing(3)
            self.vmap_selector = PathSelector(
                "vmap file",
                get_setting(self.settings, "fields", "vmap_file", ""),
                file_filter="Valve map files (*.vmap);;All files (*.*)",
            )
            world_layout.addWidget(self.vmap_selector)
            world_options = QHBoxLayout()
            world_options.setContentsMargins(0, 2, 0, 2)
            world_options.setSpacing(10)
            self.build_world_checkbox = QCheckBox("build world")
            self.build_world_checkbox.setChecked(get_bool_setting(self.settings, "checkboxes", "build_world", True))
            self.entities_only_checkbox = QCheckBox("entities only")
            self.entities_only_checkbox.setChecked(get_bool_setting(self.settings, "checkboxes", "entities_only", False))
            self.presolve_physics_checkbox = QCheckBox("pre-settle physics objects")
            self.presolve_physics_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "presettle_physics", True)
            )
            world_options.addWidget(self.build_world_checkbox)
            world_options.addWidget(self.entities_only_checkbox)
            world_options.addWidget(self.presolve_physics_checkbox)
            world_options.addStretch(1)
            world_layout.addLayout(world_options)
            compiler_groups.addWidget(world_group, 0, 0, 1, 3)

            baked_lighting_group = QGroupBox("baked lighting")
            baked_lighting_layout = QVBoxLayout(baked_lighting_group)
            baked_lighting_layout.setContentsMargins(8, 8, 8, 8)
            baked_lighting_layout.setSpacing(3)
            baked_lighting_options = QGridLayout()
            baked_lighting_options.setContentsMargins(0, 2, 0, 2)
            baked_lighting_options.setHorizontalSpacing(10)
            baked_lighting_options.setVerticalSpacing(3)
            self.generate_lightmaps_checkbox = QCheckBox("generate lightmaps")
            self.generate_lightmaps_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "generate_lightmaps", True)
            )
            self.noise_removal_checkbox = QCheckBox("noise removal")
            self.noise_removal_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "noise_removal", True)
            )
            self.disable_lighting_calculations_checkbox = QCheckBox(
                "disable lighting calculations (debug texel density / chart allocation)"
            )
            self.disable_lighting_calculations_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "disable_lighting_calculations", False)
            )
            self.lightmap_compression_checkbox = QCheckBox("compression")
            self.lightmap_compression_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "lightmap_compression", True)
            )
            baked_lighting_options.addWidget(self.generate_lightmaps_checkbox, 0, 0)
            baked_lighting_options.addWidget(self.noise_removal_checkbox, 0, 1)
            baked_lighting_options.addWidget(self.disable_lighting_calculations_checkbox, 1, 0, 1, 2)
            baked_lighting_options.addWidget(self.lightmap_compression_checkbox, 2, 0)
            baked_lighting_layout.addLayout(baked_lighting_options)

            baked_lighting_fields = QGridLayout()
            baked_lighting_fields.setContentsMargins(0, 2, 0, 2)
            baked_lighting_fields.setHorizontalSpacing(6)
            baked_lighting_fields.setVerticalSpacing(3)
            baked_lighting_fields.addWidget(QLabel("resolution"), 0, 0)
            self.lightmap_resolution_combo = QComboBox()
            self.lightmap_resolution_combo.addItems(["512", "1024", "2048", "4096", "8192"])
            self.lightmap_resolution_combo.setCurrentText(
                get_setting(self.settings, "fields", "lightmap_resolution", "512")
            )
            self.lightmap_resolution_combo.setFixedHeight(26)
            self.lightmap_resolution_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            baked_lighting_fields.addWidget(self.lightmap_resolution_combo, 0, 1)
            baked_lighting_fields.addWidget(QLabel("quality"), 0, 2)
            self.lightmap_quality_combo = QComboBox()
            self.lightmap_quality_combo.addItems(["fast", "standard", "final"])
            self.lightmap_quality_combo.setCurrentText(
                get_setting(self.settings, "fields", "lightmap_quality", "standard")
            )
            self.lightmap_quality_combo.setFixedHeight(26)
            self.lightmap_quality_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            baked_lighting_fields.addWidget(self.lightmap_quality_combo, 0, 3)
            baked_lighting_fields.setColumnStretch(4, 1)
            baked_lighting_layout.addLayout(baked_lighting_fields)
            compiler_groups.addWidget(baked_lighting_group, 1, 0)

            misc_group = QGroupBox("misc")
            misc_layout = QVBoxLayout(misc_group)
            misc_layout.setContentsMargins(8, 8, 8, 8)
            misc_layout.setSpacing(3)
            misc_options = QGridLayout()
            misc_options.setContentsMargins(0, 2, 0, 2)
            misc_options.setHorizontalSpacing(10)
            misc_options.setVerticalSpacing(3)
            self.build_physics_checkbox = QCheckBox("build physics")
            self.build_physics_checkbox.setChecked(get_bool_setting(self.settings, "checkboxes", "build_physics", True))
            self.build_visibility_checkbox = QCheckBox("build visibility")
            self.build_visibility_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "build_visibility", False)
            )
            self.build_navigation_checkbox = QCheckBox("build navigation")
            self.build_navigation_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "build_navigation", True)
            )
            misc_options.addWidget(self.build_physics_checkbox, 0, 0)
            misc_options.addWidget(self.build_visibility_checkbox, 0, 1)
            misc_options.addWidget(self.build_navigation_checkbox, 1, 0)
            misc_layout.addLayout(misc_options)
            compiler_groups.addWidget(misc_group, 1, 1)

            steam_audio_group = QGroupBox("steam audio")
            steam_audio_layout = QVBoxLayout(steam_audio_group)
            steam_audio_layout.setContentsMargins(8, 8, 8, 8)
            steam_audio_layout.setSpacing(3)
            steam_audio_options = QGridLayout()
            steam_audio_options.setContentsMargins(0, 2, 0, 2)
            steam_audio_options.setHorizontalSpacing(10)
            steam_audio_options.setVerticalSpacing(3)
            self.bake_reverb_checkbox = QCheckBox("bake reverb")
            self.bake_reverb_checkbox.setChecked(get_bool_setting(self.settings, "checkboxes", "bake_reverb", True))
            self.bake_paths_checkbox = QCheckBox("bake paths")
            self.bake_paths_checkbox.setChecked(get_bool_setting(self.settings, "checkboxes", "bake_paths", True))
            self.bake_custom_data_checkbox = QCheckBox("bake custom data")
            self.bake_custom_data_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "bake_custom_data", True)
            )
            self.strict_bake_mode_checkbox = QCheckBox("strict bake mode")
            self.strict_bake_mode_checkbox.setChecked(
                get_bool_setting(self.settings, "checkboxes", "strict_bake_mode", False)
            )
            steam_audio_options.addWidget(self.bake_reverb_checkbox, 0, 0)
            steam_audio_options.addWidget(self.bake_paths_checkbox, 0, 1)
            steam_audio_options.addWidget(self.bake_custom_data_checkbox, 1, 0)
            steam_audio_options.addWidget(self.strict_bake_mode_checkbox, 1, 1)
            steam_audio_layout.addLayout(steam_audio_options)
            steam_audio_fields = QGridLayout()
            steam_audio_fields.setContentsMargins(0, 2, 0, 2)
            steam_audio_fields.setHorizontalSpacing(6)
            steam_audio_fields.addWidget(QLabel("threads"), 0, 0)
            self.steam_audio_threads_entry = QLineEdit(get_setting(self.settings, "fields", "steam_audio_threads", "8"))
            self.steam_audio_threads_entry.setFixedWidth(70)
            self.steam_audio_threads_entry.setFixedHeight(26)
            self.steam_audio_threads_entry.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            steam_audio_fields.addWidget(self.steam_audio_threads_entry, 0, 1)
            steam_audio_fields.setColumnStretch(2, 1)
            steam_audio_layout.addLayout(steam_audio_fields)
            compiler_groups.addWidget(steam_audio_group, 1, 2)

            command_line_group = QGroupBox("command line")
            command_line_layout = QVBoxLayout(command_line_group)
            command_line_layout.setContentsMargins(8, 8, 8, 8)
            command_line_layout.setSpacing(3)
            self.compiler_command_text = QTextEdit()
            self.compiler_command_text.setReadOnly(True)
            self.compiler_command_text.setFixedHeight(54)
            self.compiler_command_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            command_line_layout.addWidget(self.compiler_command_text)
            compiler_groups.addWidget(command_line_group, 2, 0, 1, 3)

            compiler_groups.setColumnStretch(0, 1)
            compiler_groups.setColumnStretch(1, 1)
            compiler_groups.setColumnStretch(2, 1)
            map_compiler_layout.addLayout(compiler_groups)
            build_layout = QHBoxLayout()
            build_layout.setContentsMargins(0, 2, 0, 2)
            build_layout.addStretch(1)
            self.build_map_button = QPushButton("Build")
            self.build_map_button.setMinimumWidth(90)
            self.build_map_button.setFixedHeight(26)
            self.build_map_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.build_map_button.clicked.connect(self.build_map)
            build_layout.addWidget(self.build_map_button)
            map_compiler_layout.addLayout(build_layout)
            map_compiler_layout.addStretch(1)
            tabs.addTab(map_compiler_section, "map compiler")
            self.connect_compiler_command_updates()
            self.update_compiler_preset_buttons()
            self.update_compiler_command_line()

            autojoiner_section = QWidget()
            autojoiner_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            autojoiner_section_layout = QVBoxLayout(autojoiner_section)
            autojoiner_section_layout.setContentsMargins(8, 8, 8, 8)
            autojoiner_section_layout.setSpacing(3)
            autojoiner_section_layout.setAlignment(Qt.AlignTop)
            autojoiner_layout = QGridLayout()
            autojoiner_layout.setContentsMargins(0, 2, 0, 2)
            autojoiner_layout.setHorizontalSpacing(6)
            autojoiner_layout.setVerticalSpacing(0)
            ip_label = QLabel("ip")
            ip_label.setFixedHeight(26)
            autojoiner_layout.addWidget(ip_label, 0, 0)
            self.autojoiner_ip_entry = QLineEdit(get_setting(self.settings, "fields", "autojoiner_ip", ""))
            self.autojoiner_ip_entry.setMinimumWidth(180)
            self.autojoiner_ip_entry.setFixedHeight(26)
            self.autojoiner_ip_entry.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            autojoiner_layout.addWidget(self.autojoiner_ip_entry, 0, 1)
            port_label = QLabel("port")
            port_label.setFixedHeight(26)
            autojoiner_layout.addWidget(port_label, 0, 2)
            self.autojoiner_port_entry = QLineEdit(get_setting(self.settings, "fields", "autojoiner_port", ""))
            self.autojoiner_port_entry.setFixedWidth(80)
            self.autojoiner_port_entry.setFixedHeight(26)
            self.autojoiner_port_entry.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            autojoiner_layout.addWidget(self.autojoiner_port_entry, 0, 3)
            name_label = QLabel("name")
            name_label.setFixedHeight(26)
            autojoiner_layout.addWidget(name_label, 0, 4)
            self.autojoiner_name_entry = QLineEdit(get_setting(self.settings, "fields", "autojoiner_name", ""))
            self.autojoiner_name_entry.setFixedWidth(140)
            self.autojoiner_name_entry.setFixedHeight(26)
            self.autojoiner_name_entry.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            autojoiner_layout.addWidget(self.autojoiner_name_entry, 0, 5)
            self.autojoiner_toggle_button = QPushButton("Start")
            self.autojoiner_toggle_button.setMinimumWidth(70)
            self.autojoiner_toggle_button.setFixedHeight(26)
            self.autojoiner_toggle_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.autojoiner_toggle_button.clicked.connect(self.toggle_autojoiner)
            autojoiner_layout.addWidget(self.autojoiner_toggle_button, 0, 6)
            autojoiner_layout.setColumnStretch(1, 1)
            autojoiner_section_layout.addLayout(autojoiner_layout)
            tabs.addTab(autojoiner_section, "autojoiner")
            outer.addWidget(tabs)

            outer.addWidget(QLabel("console"))
            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.document().setMaximumBlockCount(CONSOLE_MAX_LINES)
            self.log_text.setMinimumHeight(90)
            self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            outer.addWidget(self.log_text, 1)
            self.update_autojoiner_state()
            QTimer.singleShot(0, self.resize_for_current_tab)

        def resize_for_current_tab(self):
            if not hasattr(self, "tabs"):
                return

            current_tab = self.tabs.currentWidget()
            if current_tab is None:
                return

            tab_bar_height = self.tabs.tabBar().sizeHint().height()
            tab_padding = 24
            fixed_height = 8 + 34 + 4 + 4 + 18 + 90 + 8
            target_height = max(
                MIN_WINDOW_HEIGHT,
                current_tab.sizeHint().height() + tab_bar_height + tab_padding + fixed_height,
            )
            self.setMinimumHeight(target_height)
            self.resize(max(self.width(), self.minimumWidth()), target_height)

        def clear_log(self):
            self.compiler_output_buffer = ""
            self.log_text.clear()

        def log(self, message, color=None):
            if color is None and str(message).startswith("ERROR:"):
                color = "#ff5c5c"

            if color:
                self.log_text.append(f'<span style="color: {color};">{html.escape(str(message))}</span>')
            else:
                self.log_text.append(str(message))
            QApplication.processEvents()

        def append_log_text(self, text):
            output = self.format_compiler_output_chunk(str(text))
            if not output:
                return

            self.log_text.moveCursor(QTextCursor.End)
            self.log_text.insertHtml(output)
            self.log_text.ensureCursorVisible()
            QApplication.processEvents()

        def format_compiler_output_chunk(self, text, flush=False):
            self.compiler_output_buffer += text
            if flush:
                chunk = self.compiler_output_buffer
                self.compiler_output_buffer = ""
                return self.prepare_compiler_output_html(chunk)

            split_at = len(self.compiler_output_buffer)
            last_amp = self.compiler_output_buffer.rfind("&")
            if last_amp != -1 and ";" not in self.compiler_output_buffer[last_amp:] and len(self.compiler_output_buffer) - last_amp <= 16:
                split_at = min(split_at, last_amp)

            last_lt = self.compiler_output_buffer.rfind("<")
            last_gt = self.compiler_output_buffer.rfind(">")
            if last_lt > last_gt and len(self.compiler_output_buffer) - last_lt <= 64:
                split_at = min(split_at, last_lt)

            chunk = self.compiler_output_buffer[:split_at]
            self.compiler_output_buffer = self.compiler_output_buffer[split_at:]
            return self.prepare_compiler_output_html(chunk)

        def prepare_compiler_output_html(self, text):
            if re.search(r"(?i)<\s*(br|span|font|div|p|table|tr|td|body|html)\b", text):
                return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")
            return html.escape(html.unescape(text)).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")

        def flush_compiler_output(self):
            output = self.format_compiler_output_chunk("", flush=True)
            if output:
                self.log_text.moveCursor(QTextCursor.End)
                self.log_text.insertHtml(output)
                self.log_text.ensureCursorVisible()
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

            field_enabled = not launch_option_enabled and not autojoiner_running
            self.autojoiner_ip_entry.setEnabled(field_enabled)
            self.autojoiner_port_entry.setEnabled(field_enabled)
            self.autojoiner_name_entry.setEnabled(field_enabled)
            self.autojoiner_toggle_button.setEnabled(not launch_option_enabled)
            self.autojoiner_toggle_button.setText("Stop" if autojoiner_running else "Start")

        def detect_resourcecompiler_path(self):
            return find_resourcecompiler_path(Path(self.cs2_root_selector.get_path()))

        def connect_compiler_command_updates(self):
            checkboxes = [
                self.build_world_checkbox,
                self.entities_only_checkbox,
                self.presolve_physics_checkbox,
                self.generate_lightmaps_checkbox,
                self.noise_removal_checkbox,
                self.disable_lighting_calculations_checkbox,
                self.lightmap_compression_checkbox,
                self.build_physics_checkbox,
                self.build_visibility_checkbox,
                self.build_navigation_checkbox,
                self.bake_reverb_checkbox,
                self.bake_paths_checkbox,
                self.bake_custom_data_checkbox,
                self.strict_bake_mode_checkbox,
            ]
            for checkbox in checkboxes:
                checkbox.stateChanged.connect(self.update_compiler_command_line)
                checkbox.stateChanged.connect(self.mark_compiler_preset_custom)

            self.lightmap_resolution_combo.currentTextChanged.connect(self.update_compiler_command_line)
            self.lightmap_resolution_combo.currentTextChanged.connect(self.mark_compiler_preset_custom)
            self.lightmap_quality_combo.currentTextChanged.connect(self.update_compiler_command_line)
            self.lightmap_quality_combo.currentTextChanged.connect(self.mark_compiler_preset_custom)
            self.resourcecompiler_selector.entry.textChanged.connect(self.update_compiler_command_line)
            self.vmap_selector.entry.textChanged.connect(self.update_compiler_command_line)
            self.steam_audio_threads_entry.textChanged.connect(self.update_compiler_command_line)
            self.steam_audio_threads_entry.textChanged.connect(self.mark_compiler_preset_custom)

        def mark_compiler_preset_custom(self, *_args):
            if self.applying_compiler_preset:
                return

            if self.compiler_preset_combo.currentText() != "custom":
                self.compiler_preset_combo.blockSignals(True)
                self.compiler_preset_combo.setCurrentText("custom")
                self.compiler_preset_combo.blockSignals(False)
                self.update_compiler_preset_buttons()

        def apply_compiler_preset(self, preset):
            self.update_compiler_preset_buttons()
            if preset == "custom":
                return

            self.applying_compiler_preset = True
            if preset in self.custom_compiler_presets:
                self.apply_compiler_preset_values(self.custom_compiler_presets[preset])
                self.applying_compiler_preset = False
                self.update_compiler_command_line()
                return

            for checkbox in (
                self.build_world_checkbox,
                self.entities_only_checkbox,
                self.presolve_physics_checkbox,
                self.generate_lightmaps_checkbox,
                self.noise_removal_checkbox,
                self.disable_lighting_calculations_checkbox,
                self.lightmap_compression_checkbox,
                self.build_physics_checkbox,
                self.build_visibility_checkbox,
                self.build_navigation_checkbox,
                self.bake_reverb_checkbox,
                self.bake_paths_checkbox,
                self.bake_custom_data_checkbox,
                self.strict_bake_mode_checkbox,
            ):
                checkbox.setChecked(False)

            if preset in ("full compile", "final compile"):
                for checkbox in (
                    self.build_world_checkbox,
                    self.presolve_physics_checkbox,
                    self.generate_lightmaps_checkbox,
                    self.build_physics_checkbox,
                    self.build_visibility_checkbox,
                    self.build_navigation_checkbox,
                    self.bake_reverb_checkbox,
                    self.bake_paths_checkbox,
                    self.bake_custom_data_checkbox,
                    self.strict_bake_mode_checkbox,
                ):
                    checkbox.setChecked(True)

                if preset == "final compile":
                    self.lightmap_resolution_combo.setCurrentText("2048")
                    self.lightmap_quality_combo.setCurrentText("final")
                else:
                    self.lightmap_resolution_combo.setCurrentText("1024")
                    self.lightmap_quality_combo.setCurrentText("standard")
            elif preset == "fast compile":
                for checkbox in (
                    self.build_world_checkbox,
                    self.presolve_physics_checkbox,
                    self.build_physics_checkbox,
                    self.build_navigation_checkbox,
                    self.strict_bake_mode_checkbox,
                ):
                    checkbox.setChecked(True)

            elif preset == "only entities":
                for checkbox in (
                    self.build_world_checkbox,
                    self.entities_only_checkbox,
                    self.presolve_physics_checkbox,
                ):
                    checkbox.setChecked(True)

            self.steam_audio_threads_entry.setText("8")
            self.applying_compiler_preset = False
            self.update_compiler_command_line()

        def update_compiler_preset_buttons(self):
            selected_preset = self.compiler_preset_combo.currentText()
            self.save_compiler_preset_button.setEnabled(selected_preset == "custom")
            self.delete_compiler_preset_button.setEnabled(selected_preset in self.custom_compiler_presets)

        def apply_compiler_preset_values(self, values):
            checkbox_values = {
                self.build_world_checkbox: "build_world",
                self.entities_only_checkbox: "entities_only",
                self.presolve_physics_checkbox: "presettle_physics",
                self.generate_lightmaps_checkbox: "generate_lightmaps",
                self.noise_removal_checkbox: "noise_removal",
                self.disable_lighting_calculations_checkbox: "disable_lighting_calculations",
                self.lightmap_compression_checkbox: "lightmap_compression",
                self.build_physics_checkbox: "build_physics",
                self.build_visibility_checkbox: "build_visibility",
                self.build_navigation_checkbox: "build_navigation",
                self.bake_reverb_checkbox: "bake_reverb",
                self.bake_paths_checkbox: "bake_paths",
                self.bake_custom_data_checkbox: "bake_custom_data",
                self.strict_bake_mode_checkbox: "strict_bake_mode",
            }
            for checkbox, key in checkbox_values.items():
                checkbox.setChecked(bool(values.get(key, False)))

            self.lightmap_resolution_combo.setCurrentText(str(values.get("lightmap_resolution", "512")))
            self.lightmap_quality_combo.setCurrentText(str(values.get("lightmap_quality", "standard")))
            self.steam_audio_threads_entry.setText(str(values.get("steam_audio_threads", "8")))

        def capture_compiler_preset_values(self):
            return {
                "build_world": self.build_world_checkbox.isChecked(),
                "entities_only": self.entities_only_checkbox.isChecked(),
                "presettle_physics": self.presolve_physics_checkbox.isChecked(),
                "generate_lightmaps": self.generate_lightmaps_checkbox.isChecked(),
                "noise_removal": self.noise_removal_checkbox.isChecked(),
                "disable_lighting_calculations": self.disable_lighting_calculations_checkbox.isChecked(),
                "lightmap_compression": self.lightmap_compression_checkbox.isChecked(),
                "build_physics": self.build_physics_checkbox.isChecked(),
                "build_visibility": self.build_visibility_checkbox.isChecked(),
                "build_navigation": self.build_navigation_checkbox.isChecked(),
                "bake_reverb": self.bake_reverb_checkbox.isChecked(),
                "bake_paths": self.bake_paths_checkbox.isChecked(),
                "bake_custom_data": self.bake_custom_data_checkbox.isChecked(),
                "strict_bake_mode": self.strict_bake_mode_checkbox.isChecked(),
                "lightmap_resolution": self.lightmap_resolution_combo.currentText(),
                "lightmap_quality": self.lightmap_quality_combo.currentText(),
                "steam_audio_threads": self.steam_audio_threads_entry.text().strip(),
            }

        def save_custom_compiler_preset(self):
            if self.compiler_preset_combo.currentText() != "custom":
                QMessageBox.critical(self, "Custom preset required", "Select custom before saving a custom preset.")
                return

            name, accepted = QInputDialog.getText(self, "Save custom preset", "Preset name:")
            name = name.strip()
            if not accepted or not name:
                return

            built_in_names = {"custom", *BUILT_IN_COMPILER_PRESETS}
            if name in built_in_names:
                QMessageBox.critical(self, "Invalid preset name", "Choose a name that does not match a built-in preset.")
                return

            self.custom_compiler_presets[name] = self.capture_compiler_preset_values()
            save_custom_compiler_presets(self.custom_compiler_presets)
            if self.compiler_preset_combo.findText(name) == -1:
                self.compiler_preset_combo.addItem(name)
            self.compiler_preset_combo.setCurrentText(name)
            self.update_compiler_preset_buttons()

        def delete_custom_compiler_preset(self):
            name = self.compiler_preset_combo.currentText()
            if name not in self.custom_compiler_presets:
                return

            del self.custom_compiler_presets[name]
            save_custom_compiler_presets(self.custom_compiler_presets)
            item_index = self.compiler_preset_combo.findText(name)
            if item_index != -1:
                self.compiler_preset_combo.removeItem(item_index)
            self.compiler_preset_combo.setCurrentText("custom")
            self.update_compiler_preset_buttons()

        def update_compiler_command_line(self, *_args):
            self.compiler_command_text.setPlainText(
                subprocess.list2cmdline(self.build_resourcecompiler_command())
            )

        def build_resourcecompiler_command(self):
            compiler_path = self.resourcecompiler_selector.get_path() or "resourcecompiler.exe"
            vmap_path = self.vmap_selector.get_path()
            return build_resourcecompiler_command_from_values(
                compiler_path,
                vmap_path,
                self.capture_compiler_preset_values(),
            )

        def get_steam_audio_thread_count(self):
            value = self.steam_audio_threads_entry.text().strip()
            if value.isdigit() and int(value) > 0:
                return value
            return "8"

        def build_map(self):
            compiler_path = Path(self.resourcecompiler_selector.get_path())
            if not compiler_path.is_file():
                self.fail("Build failed", "Select a valid resourcecompiler.exe first.")
                return

            vmap_path = Path(self.vmap_selector.get_path())
            if not vmap_path.is_file() or vmap_path.suffix.lower() != ".vmap":
                self.fail("Build failed", "Select a valid .vmap file first.")
                return

            command = self.build_resourcecompiler_command()
            self.clear_log()
            self.log("Starting map build.")
            self.log(subprocess.list2cmdline(command))
            self.build_map_button.setEnabled(False)
            threading.Thread(
                target=self.run_resourcecompiler_thread,
                args=(command, compiler_path.parent, Path(self.cs2_root_selector.get_path())),
                daemon=True,
            ).start()

        def run_resourcecompiler_thread(self, command, working_directory, cs2_root):
            started_at = time.perf_counter()
            exit_code = -1
            compiler_launch_state = None
            try:
                compiler_launch_state = prepare_map_compile_launch_state(cs2_root, self.thread_log)
                process = subprocess.Popen(
                    command,
                    cwd=str(working_directory),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                if process.stdout:
                    pending_output = []
                    last_flush = time.perf_counter()
                    while True:
                        chunk = process.stdout.read(1)
                        if not chunk:
                            break

                        pending_output.append(chunk)
                        now = time.perf_counter()
                        if chunk in "\r\n" or now - last_flush >= 0.1:
                            self.thread_log_raw("".join(pending_output))
                            pending_output.clear()
                            last_flush = now

                    if pending_output:
                        self.thread_log_raw("".join(pending_output))
                exit_code = process.wait()
            except OSError as error:
                self.thread_log(f"ERROR: {error}")
            finally:
                try:
                    restore_map_compile_launch_state(compiler_launch_state, self.thread_log)
                except OSError as error:
                    self.thread_log(f"ERROR: Could not restore pre-build CS2Fixes state: {error}")
                self.log_bridge.compiler_finished.emit(exit_code, time.perf_counter() - started_at)

        def on_resourcecompiler_finished(self, exit_code, elapsed_seconds):
            self.flush_compiler_output()
            self.build_map_button.setEnabled(True)
            if exit_code == 0:
                self.log(f"Map build complete in {elapsed_seconds:.2f} seconds.", "#36d675")
            else:
                self.log(f"Map build failed with exit code {exit_code} after {elapsed_seconds:.2f} seconds.", "#ff5c5c")

        def closeEvent(self, event):
            self.autojoiner_stop_event.set()
            save_settings(
                self.cs2_root_selector.get_path(),
                self.steamid64_input.get_value(),
                self.cs2fixes_cfg_selector.get_path(),
                self.resourcecompiler_selector.get_path(),
                self.vmap_selector.get_path(),
                self.autojoiner_ip_entry.text().strip(),
                self.autojoiner_port_entry.text().strip(),
                self.autojoiner_name_entry.text().strip(),
                self.selectors,
                self.load_cs2fixes_checkbox.isChecked(),
                self.launch_workshop_checkbox.isChecked(),
                self.build_world_checkbox.isChecked(),
                self.entities_only_checkbox.isChecked(),
                self.presolve_physics_checkbox.isChecked(),
                self.generate_lightmaps_checkbox.isChecked(),
                self.noise_removal_checkbox.isChecked(),
                self.disable_lighting_calculations_checkbox.isChecked(),
                self.lightmap_compression_checkbox.isChecked(),
                self.lightmap_resolution_combo.currentText(),
                self.lightmap_quality_combo.currentText(),
                self.build_physics_checkbox.isChecked(),
                self.build_visibility_checkbox.isChecked(),
                self.build_navigation_checkbox.isChecked(),
                self.bake_reverb_checkbox.isChecked(),
                self.bake_paths_checkbox.isChecked(),
                self.bake_custom_data_checkbox.isChecked(),
                self.strict_bake_mode_checkbox.isChecked(),
                self.steam_audio_threads_entry.text().strip(),
                self.custom_compiler_presets,
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

            if self.load_cs2fixes_checkbox.isChecked() or self.launch_workshop_checkbox.isChecked():
                self.fail("Autojoiner failed", "Disable cs2fixes and workshop tools before starting the autojoiner.")
                return

            cs2_root = Path(self.cs2_root_selector.get_path())
            if not cs2_root.is_dir():
                self.fail("Invalid CS2 root", "Select a valid CS2 root directory first.")
                return

            try:
                self.log("Preparing normal CS2 launch for autojoiner.")
                launch_game_with_options(cs2_root, False, False, self.log)
            except FileNotFoundError as error:
                self.fail("Autojoiner failed", f"Could not find required file:\n{missing_file_text(error)}")
                return
            except OSError as error:
                self.fail("Autojoiner failed", str(error))
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

        def thread_log_raw(self, text):
            self.log_bridge.raw_text.emit(text)

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
    settings.optionxform = str
    if SETTINGS_FILE.is_file():
        settings.read(SETTINGS_FILE, encoding="utf-8")

    return settings


def load_custom_compiler_presets(settings):
    if not settings.has_section("compiler_presets"):
        return {}

    presets = {}
    for name, raw_value in settings.items("compiler_presets"):
        try:
            preset = json.loads(raw_value)
        except json.JSONDecodeError:
            continue
        if isinstance(preset, dict):
            presets[name] = preset

    return presets


def save_custom_compiler_presets(presets):
    settings = load_settings()
    if settings.has_section("compiler_presets"):
        settings.remove_section("compiler_presets")
    settings.add_section("compiler_presets")
    for name, preset in sorted(presets.items()):
        settings.set("compiler_presets", name, json.dumps(preset, sort_keys=True))

    with SETTINGS_FILE.open("w", encoding="utf-8") as settings_file:
        settings.write(settings_file)


def save_settings(
    cs2_root,
    steamid64,
    cs2fixes_cfg,
    resourcecompiler,
    vmap_file,
    autojoiner_ip,
    autojoiner_port,
    autojoiner_name,
    selectors,
    launch_with_cs2fixes,
    launch_workshop,
    build_world,
    entities_only,
    presettle_physics,
    generate_lightmaps,
    noise_removal,
    disable_lighting_calculations,
    lightmap_compression,
    lightmap_resolution,
    lightmap_quality,
    build_physics,
    build_visibility,
    build_navigation,
    bake_reverb,
    bake_paths,
    bake_custom_data,
    strict_bake_mode,
    steam_audio_threads,
    custom_compiler_presets,
):
    settings = configparser.ConfigParser()
    settings.optionxform = str
    settings["fields"] = {
        "cs2_root": cs2_root,
        "steamid64": steamid64,
        "cs2fixes_cfg": cs2fixes_cfg,
        "resourcecompiler": resourcecompiler,
        "vmap_file": vmap_file,
        "lightmap_resolution": lightmap_resolution,
        "lightmap_quality": lightmap_quality,
        "steam_audio_threads": steam_audio_threads,
        "autojoiner_ip": autojoiner_ip,
        "autojoiner_port": autojoiner_port,
        "autojoiner_name": autojoiner_name,
    }

    for label, selector in selectors.items():
        settings["fields"][zip_setting_key(label)] = selector.get_path()

    settings["checkboxes"] = {
        "launch_with_cs2fixes": str(bool(launch_with_cs2fixes)),
        "launch_workshop": str(bool(launch_workshop)),
        "build_world": str(bool(build_world)),
        "entities_only": str(bool(entities_only)),
        "presettle_physics": str(bool(presettle_physics)),
        "generate_lightmaps": str(bool(generate_lightmaps)),
        "noise_removal": str(bool(noise_removal)),
        "disable_lighting_calculations": str(bool(disable_lighting_calculations)),
        "lightmap_compression": str(bool(lightmap_compression)),
        "build_physics": str(bool(build_physics)),
        "build_visibility": str(bool(build_visibility)),
        "build_navigation": str(bool(build_navigation)),
        "bake_reverb": str(bool(bake_reverb)),
        "bake_paths": str(bool(bake_paths)),
        "bake_custom_data": str(bool(bake_custom_data)),
        "strict_bake_mode": str(bool(strict_bake_mode)),
    }

    if custom_compiler_presets:
        settings["compiler_presets"] = {
            name: json.dumps(preset, sort_keys=True)
            for name, preset in sorted(custom_compiler_presets.items())
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


def find_resourcecompiler_path(cs2_root):
    if cs2_root and cs2_root.is_dir():
        candidate = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
        if candidate.is_file():
            return str(candidate)

    detected_root = find_cs2_root()
    if detected_root:
        candidate = Path(detected_root) / "game" / "bin" / "win64" / "resourcecompiler.exe"
        if candidate.is_file():
            return str(candidate)

    return ""


def lightmap_quality_value(label):
    return {
        "fast": "0",
        "standard": "1",
        "final": "2",
    }.get(label, "1")


def compiler_preset_values(preset_name, custom_presets):
    if preset_name in custom_presets:
        return normalize_compiler_preset_values(custom_presets[preset_name])

    if preset_name not in BUILT_IN_COMPILER_PRESETS:
        return None

    values = normalize_compiler_preset_values({})
    if preset_name in ("full compile", "final compile"):
        values.update(
            {
                "build_world": True,
                "presettle_physics": True,
                "generate_lightmaps": True,
                "lightmap_resolution": "1024",
                "lightmap_quality": "standard",
                "build_physics": True,
                "build_visibility": True,
                "build_navigation": True,
                "bake_reverb": True,
                "bake_paths": True,
                "bake_custom_data": True,
                "strict_bake_mode": True,
                "steam_audio_threads": "8",
            }
        )
        if preset_name == "final compile":
            values["lightmap_resolution"] = "2048"
            values["lightmap_quality"] = "final"
    elif preset_name == "fast compile":
        values.update(
            {
                "build_world": True,
                "presettle_physics": True,
                "build_physics": True,
                "build_navigation": True,
                "strict_bake_mode": True,
                "steam_audio_threads": "8",
            }
        )
    elif preset_name == "only entities":
        values.update(
            {
                "build_world": True,
                "entities_only": True,
                "presettle_physics": True,
                "steam_audio_threads": "8",
            }
        )

    return values


def normalize_compiler_preset_values(values):
    defaults = {
        "build_world": False,
        "entities_only": False,
        "presettle_physics": False,
        "generate_lightmaps": False,
        "noise_removal": False,
        "disable_lighting_calculations": False,
        "lightmap_compression": False,
        "build_physics": False,
        "build_visibility": False,
        "build_navigation": False,
        "bake_reverb": False,
        "bake_paths": False,
        "bake_custom_data": False,
        "strict_bake_mode": False,
        "lightmap_resolution": "512",
        "lightmap_quality": "standard",
        "steam_audio_threads": "8",
    }
    normalized = defaults.copy()
    normalized.update(values)
    return normalized


def build_resourcecompiler_command_from_values(compiler_path, vmap_path, values):
    steam_audio_thread_count = str(values.get("steam_audio_threads") or "8")
    args = [
        str(compiler_path),
        "-threads",
        "7",
        "-fshallow",
        "-maxtextureres",
        "256",
        "-quiet",
        "-html",
        "-unbufferedio",
    ]

    if vmap_path:
        args.extend(["-i", str(vmap_path)])

    args.append("-noassert")

    if values.get("build_world"):
        args.append("-world")
    if values.get("entities_only"):
        args.append("-entities")
    if values.get("presettle_physics"):
        args.append("-rebake_surfacegraph")
    if values.get("generate_lightmaps"):
        args.extend(
            [
                "-bakelighting",
                "-lightmapMaxResolution",
                str(values.get("lightmap_resolution") or "512"),
                "-lightmapVRadQuality",
                lightmap_quality_value(str(values.get("lightmap_quality") or "standard")),
            ]
        )
        if not values.get("noise_removal"):
            args.append("-lightmapDisableFiltering")
        if not values.get("lightmap_compression"):
            args.append("-lightmapCompressionDisabled")
    if values.get("disable_lighting_calculations"):
        args.append("-disableLightingCalculations")
    if values.get("build_physics"):
        args.append("-phys")
    if values.get("build_visibility"):
        args.append("-vis")
    if values.get("build_navigation"):
        args.append("-nav")
    if values.get("bake_reverb"):
        args.extend(["-sareverb", "-sareverb_threads", steam_audio_thread_count])
    if values.get("bake_paths"):
        args.extend(["-sapaths", "-sareverb_threads", steam_audio_thread_count])
    if values.get("bake_custom_data"):
        args.extend(["-sacustomdata", "-sacustomdata_threads", steam_audio_thread_count])
    if values.get("strict_bake_mode"):
        args.append("-sabakestrictmode")

    args.extend(["-breakpad", "-nop4", "-outroot", str(default_hammer_outroot())])
    return args


def default_hammer_outroot():
    return Path(tempfile.gettempdir()) / "valve" / "hammermapbuild" / "game"


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
    gameinfo_path = cs2_root / "game" / "csgo" / "gameinfo.gi"
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


def prepare_map_compile_launch_state(cs2_root, log):
    bin_dir = cs2_root / "game" / "bin" / "win64"
    server_dll = bin_dir / "server.dll"
    metamod_dll = bin_dir / "metamod.2.cs2.dll"
    active = server_dll.is_file()
    state = {
        "active": active,
        "cs2_root": cs2_root,
        "workshop_filters_removed": None,
        "backup_dir": None,
        "backups": {},
    }

    if not active:
        log("Map compiler: CS2Fixes server.dll not present; no launch-state changes needed.")
        return state

    state["workshop_filters_removed"] = gameinfo_workshop_filters_removed(cs2_root)
    backup_dir = Path(tempfile.mkdtemp(prefix="cs2launcher-mapcompile-"))
    state["backup_dir"] = backup_dir
    for path in (server_dll, metamod_dll):
        if path.is_file():
            backup_path = backup_dir / path.name
            shutil.copyfile(path, backup_path)
            state["backups"][path] = backup_path

    log("Map compiler: CS2Fixes launch state detected; preparing tools-only state without launching tools.")
    update_gameinfo_workshop_filters(cs2_root, True, log)
    log(f"Deleting if present: {server_dll}")
    delete_file_if_exists(server_dll)
    return state


def restore_map_compile_launch_state(state, log):
    if not state:
        return

    try:
        if state["active"]:
            cs2_root = state["cs2_root"]
            log("Map compiler: restoring pre-build CS2Fixes launch state.")
            update_gameinfo_workshop_filters(cs2_root, state["workshop_filters_removed"], log)
            for target_path, backup_path in state["backups"].items():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(backup_path, target_path)
                log(f"Restored: {target_path}")
    finally:
        backup_dir = state.get("backup_dir")
        if backup_dir:
            shutil.rmtree(backup_dir, ignore_errors=True)


def gameinfo_workshop_filters_removed(cs2_root):
    gameinfo_path = cs2_root / "game" / "csgo" / "gameinfo.gi"
    if not gameinfo_path.is_file():
        raise FileNotFoundError(gameinfo_path)

    content = gameinfo_path.read_text(encoding="utf-8-sig")
    return not has_all_gameinfo_workshop_lines(content.splitlines(keepends=True))


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
            info = a2s.info(server_addr, timeout=A2S_TIMEOUT_SECONDS)
            current_players = info.player_count
            max_players = info.max_players
            map_name = info.map_name
            log(f"[{system_time()}] {map_name} - player count: {current_players}/{max_players}")

            if connect_attempted:
                log(f"checking for '{player_name}'")
                try:
                    players = a2s.players(server_addr, timeout=A2S_TIMEOUT_SECONDS)
                except Exception as error:
                    log(f"Player query failed: {error}")
                else:
                    if any(name_matches(player.name, player_name) for player in players):
                        log(f"Detected player '{player_name}' in server; stopping autojoiner.")
                        play_success_sound()
                        return

            if connect_attempted and time.monotonic() >= player_check_until:
                connect_attempted = False
                player_check_until = None

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


def cli_uses_color():
    return os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb"


def cli_color_text(text, color):
    if not cli_uses_color():
        return text

    return f"{color}{text}{ANSI_RESET}"


def cli_print(text, color=None, file=None):
    print(cli_color_text(text, color) if color else text, file=file or sys.stdout)


def stream_compiler_output_to_terminal(stream):
    formatter = TerminalCompilerOutputFormatter(cli_uses_color())
    for chunk in iter(lambda: stream.read(1), ""):
        output = formatter.feed(chunk)
        if output:
            sys.stdout.write(output)
            sys.stdout.flush()

    output = formatter.flush()
    if output:
        sys.stdout.write(output)
        sys.stdout.flush()


class TerminalCompilerOutputFormatter:
    def __init__(self, use_color):
        self.buffer = ""
        self.use_color = use_color

    def feed(self, text):
        self.buffer += text
        split_at = len(self.buffer)

        last_amp = self.buffer.rfind("&")
        if last_amp != -1 and ";" not in self.buffer[last_amp:] and len(self.buffer) - last_amp <= 16:
            split_at = min(split_at, last_amp)

        last_lt = self.buffer.rfind("<")
        last_gt = self.buffer.rfind(">")
        if last_lt > last_gt and len(self.buffer) - last_lt <= 128:
            split_at = min(split_at, last_lt)

        chunk = self.buffer[:split_at]
        self.buffer = self.buffer[split_at:]
        return self.clean(chunk)

    def flush(self):
        chunk = self.buffer
        self.buffer = ""
        return self.clean(chunk)

    def clean(self, text):
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        if self.use_color:
            text = self.apply_ansi_colors(text)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text)

    def apply_ansi_colors(self, text):
        text = re.sub(
            r'(?is)<(?:span|font)\b[^>]*(?:color\s*:\s*["\']?|color\s*=\s*["\']?)(#[0-9a-f]{6}|[a-z]+)[^>]*>',
            lambda match: ansi_color_for_html_color(match.group(1)),
            text,
        )
        return re.sub(r"(?is)</(?:span|font)>", ANSI_RESET, text)


def ansi_color_for_html_color(color):
    color = color.strip().lower()
    named_colors = {
        "red": ANSI_RED,
        "green": ANSI_GREEN,
        "yellow": ANSI_YELLOW,
        "blue": ANSI_BLUE,
        "magenta": ANSI_MAGENTA,
        "cyan": ANSI_CYAN,
        "white": ANSI_WHITE,
        "gray": ANSI_GRAY,
        "grey": ANSI_GRAY,
        "orange": ANSI_YELLOW,
    }
    if color in named_colors:
        return named_colors[color]

    if re.fullmatch(r"#[0-9a-f]{6}", color):
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
        if red >= green and red >= blue:
            return ANSI_RED if green < 160 else ANSI_YELLOW
        if green >= red and green >= blue:
            return ANSI_GREEN
        if blue >= red and blue >= green:
            return ANSI_BLUE if red < 160 else ANSI_MAGENTA

    return ""


def run_map_build_cli(settings, cs2_root, preset_name):
    custom_presets = load_custom_compiler_presets(settings)
    values = compiler_preset_values(preset_name, custom_presets)
    if values is None:
        available_presets = ", ".join((*BUILT_IN_COMPILER_PRESETS, *sorted(custom_presets)))
        cli_print(f"Unknown build preset: {preset_name}", ANSI_RED, file=sys.stderr)
        print(f"Available presets: {available_presets}", file=sys.stderr)
        return 2

    compiler_path = Path(get_setting(settings, "fields", "resourcecompiler", find_resourcecompiler_path(cs2_root)))
    if not compiler_path.is_file():
        cli_print("Build failed. Select a valid resourcecompiler.exe in the GUI first.", ANSI_RED, file=sys.stderr)
        return 1

    vmap_path = Path(get_setting(settings, "fields", "vmap_file", ""))
    if not vmap_path.is_file() or vmap_path.suffix.lower() != ".vmap":
        cli_print("Build failed. Select a valid .vmap file in the GUI first.", ANSI_RED, file=sys.stderr)
        return 1

    command = build_resourcecompiler_command_from_values(compiler_path, vmap_path, values)
    cli_print(f"Starting map build with preset: {preset_name}", ANSI_CYAN)
    print(subprocess.list2cmdline(command))

    compiler_launch_state = None
    try:
        compiler_launch_state = prepare_map_compile_launch_state(cs2_root, print)
        started_at = time.perf_counter()
        process = subprocess.Popen(
            command,
            cwd=str(compiler_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if process.stdout:
            stream_compiler_output_to_terminal(process.stdout)

        exit_code = process.wait()
        elapsed_seconds = time.perf_counter() - started_at
        if exit_code == 0:
            cli_print(f"\nMap build complete in {elapsed_seconds:.2f} seconds.", ANSI_GREEN)
        else:
            cli_print(
                f"\nMap build failed with exit code {exit_code} after {elapsed_seconds:.2f} seconds.",
                ANSI_RED,
                file=sys.stderr,
            )
        return exit_code
    except FileNotFoundError as error:
        cli_print(f"Build failed. Could not find required file: {missing_file_text(error)}", ANSI_RED, file=sys.stderr)
        return 1
    except OSError as error:
        cli_print(f"Build failed. {error}", ANSI_RED, file=sys.stderr)
        return 1
    finally:
        try:
            restore_map_compile_launch_state(compiler_launch_state, print)
        except OSError as error:
            cli_print(f"Could not restore pre-build CS2Fixes state: {error}", ANSI_RED, file=sys.stderr)


def run_cli(args):
    settings = load_settings()
    cs2_root = Path(get_setting(settings, "fields", "cs2_root", find_cs2_root()))

    if not cs2_root.is_dir():
        print("Could not find a valid CS2 root directory. Open the GUI with -gui and select it.", file=sys.stderr)
        return 1

    if args.build:
        return run_map_build_cli(settings, cs2_root, args.build)

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
    settings = load_settings()
    custom_presets = load_custom_compiler_presets(settings)
    build_preset_choices = [*BUILT_IN_COMPILER_PRESETS, *sorted(custom_presets)]
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("-gui", action="store_true", help="launch gui")
    parser.add_argument("-tools", action="store_true", help="launch workshop tools")
    parser.add_argument("-cs2fixes", action="store_true", help="launch with cs2fixes")
    parser.add_argument("-autojoiner", action="store_true", help="run autojoiner")
    parser.add_argument("-ip", help="autojoiner server IP")
    parser.add_argument("-port", type=int, help="autojoiner server port")
    parser.add_argument("-name", help="autojoiner player name to check for")
    parser.add_argument(
        "-build",
        choices=build_preset_choices,
        metavar="preset",
        help=f"build the saved .vmap with a compiler preset; available: {', '.join(build_preset_choices)}",
    )
    args = parser.parse_args(argv)

    autojoiner_flag_present = (
        args.autojoiner
        or args.ip is not None
        or args.port is not None
        or args.name is not None
    )
    if autojoiner_flag_present and (args.tools or args.cs2fixes):
        parser.error("autojoiner flags cannot be combined with -tools or -cs2fixes")

    if args.build and (args.tools or args.cs2fixes or autojoiner_flag_present):
        parser.error("-build cannot be combined with launch or autojoiner flags")

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
