"""
Non Steam Emulation - GUI (PySide6)

One single window (fixed size, matched to the artwork screen) that steps
through four pages via a QStackedWidget instead of popping separate
windows/dialogs in and out:

    1. ShortcutsPage  - intro (title/description/github link) + pick or
                         create shortcuts.vdf / browse manually / Next
    2. GameInfoWindow - back / game name / emulator path / game path / Next
    3. ArtworkWindow  - back / icon / grid / hero / logo / preview / Add
                         (left exactly as-is)
    4. DonePage       - "Game Added!" / backup path / add another,
                         restart steam, quit

"""

from __future__ import annotations

import sys
from dataclasses import dataclass

####################################


import vdf
import zlib
import shutil
import subprocess
import time
from datetime import datetime
import os
from pathlib import Path

from PySide6.QtCore import Signal


####################################

from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


ICON_FILE_FILTER    = "Icon images (*.png *.jpg *.jpeg *.ico)"
EXE_FILE_FILTER     = "Executable files (*.exe)"
ANY_FILE_FILTER     = "All files (*)"
ARTWORK_FILE_FILTER = "Images (*.png *.jpg *.jpeg)"

WINDOW_TITLE = "Non Steam Emulation"
GITHUB_URL   = "https://github.com/aaf-nope/Non-Steam-Emulation"

####################################

# Shared sizing so full-width buttons (Next / Back / the shortcuts-picker
# Next) line up with identical width and horizontal position across every
# page of the wizard.
LABEL_WIDTH         = 110
PATH_FIELD_WIDTH    = 300
BROWSE_BUTTON_WIDTH = 70
ROW_SPACING         = 10
NAME_FIELD_WIDTH    = PATH_FIELD_WIDTH + ROW_SPACING + BROWSE_BUTTON_WIDTH
TOTAL_ROW_WIDTH     = LABEL_WIDTH + ROW_SPACING + NAME_FIELD_WIDTH

# Colour language used across the redesigned pages:
#   grey  -> static text / labels
#   black -> a path once it has been chosen (read-only fields)
#   blue  -> a field the user actually types into
#   purple-> buttons
ACCENT_BLUE         = "#4C6FFF"
ACCENT_ACTION       = "#3AA0DE"
ACCENT_ACTION_HOVER = "#57B4E8"


def style_primary(button: QPushButton, radius: int = 6) -> None:
    """Apply the shared cyan-blue "primary button" look used for every
    Next / Back / Browse / action button in the redesigned UI."""
    button.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {ACCENT_ACTION};
            color: white;
            border: none;
            border-radius: {radius}px;
            font-weight: bold;
            padding: 6px;
        }}
        QPushButton:hover {{
            background-color: {ACCENT_ACTION_HOVER};
        }}
        QPushButton:disabled {{
            background-color: #a9d4ef;
            color: #f0f0f0;
        }}
        """
    )


####################################


STEAM_USERDATA = Path("C:\\Program Files (x86)\\Steam\\userdata")

SHORTCUTS_BACKUP_DIRECTORY = "shortcuts_file_backups"

# These are set at runtime by WizardController once the user confirms a
# shortcuts.vdf on the first page.
STEAM_SHORTCUTS_FILE_PATH  = ""
STEAM_SHORTCUTS_DIRECTORY  = ""
STEAM_GRID_DIRECTORY       = ""


def _is_real_user_dir(d: Path) -> bool:
    """Return True when *d* looks like a proper Steam account folder."""
    return d.is_dir() and d.name.isdigit() and d.name not in ("0",)


def discover_steam_state() -> tuple[list[str], list[Path]]:
    r"""Scan userdata\ and return (existing_vdf_paths, valid_user_dirs).

    existing_vdf_paths - every shortcuts.vdf already present on disk.
    valid_user_dirs    - every userdata\<id> folder (whether or not it has
                         a shortcuts.vdf yet).
    """
    existing: list[str] = []
    user_dirs: list[Path] = []

    if not STEAM_USERDATA.exists():
        return existing, user_dirs

    for entry in sorted(STEAM_USERDATA.iterdir()):
        if not _is_real_user_dir(entry):
            continue
        user_dirs.append(entry)
        vdf_path = entry / "config" / "shortcuts.vdf"
        if vdf_path.is_file():
            existing.append(str(vdf_path))

    return existing, user_dirs


####################################


def create_empty_shortcuts_vdf(file_path: str) -> None:
    """Write a minimal, valid binary shortcuts.vdf to *file_path*.

    The structure mirrors the real format Steam uses:
        shortcuts -> (empty dict)
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    empty_root = vdf.VDFDict()
    empty_root["shortcuts"] = vdf.VDFDict()
    with open(file_path, "wb") as f:
        vdf.binary_dump(empty_root, f)


def restart_steam() -> None:
    """Shut Steam down gracefully (if running), wait for it to exit,
    then relaunch it.
    """
    steam_path = r"C:\Program Files (x86)\Steam\steam.exe"

    if not os.path.exists(steam_path):
        return

    try:
        # Check if steam is currently running
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
            capture_output=True,
            text=True,
            check=False,
        )
        is_running = "steam.exe" in result.stdout.lower()

        if is_running:
            # --- Step 1: request graceful shutdown ---
            subprocess.run([steam_path, "-shutdown"], check=False)

            # --- Step 2: wait for all steam.exe processes to die ---
            timeout = 30          # maximum seconds to wait
            poll_interval = 1     # seconds between checks
            elapsed = 0
            while elapsed < timeout:
                time.sleep(poll_interval)
                elapsed += poll_interval
                res = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if "steam.exe" not in res.stdout.lower():
                    break  # Steam is fully gone
    except Exception as e:
        print(f"Error during Steam shutdown check: {e}")

    # --- Step 3: relaunch ---
    try:
        subprocess.Popen([steam_path])
    except Exception as e:
        print(f"Error launching Steam: {e}")


def fit_and_center(window: QWidget, fixed_size: QSize | None = None) -> None:
    window.setFixedSize(fixed_size if fixed_size is not None else window.sizeHint())
    screen = window.screen()
    if screen is not None:
        ag = screen.availableGeometry()
        window.move(
            ag.center().x() - window.width()  // 2,
            ag.center().y() - window.height() // 2,
        )


@dataclass
class GameEntry:
    """All user-collected data for a single game."""

    game_name:     str = ""
    emulator_path: str = ""
    game_path:     str = ""
    icon_path:     str = ""
    hero_path:     str = ""
    grid_path:     str = ""
    logo_path:     str = ""
    preview_path:  str = ""

    def reset(self) -> None:
        for field in self.__dataclass_fields__:
            setattr(self, field, "")


class ImagePickerButton(QPushButton):
    """Fixed-size button: shows placeholder text until an image is picked,
    then paints it zoom-to-fill with rounded corners."""

    image_selected = Signal(str)  # emits the chosen file path

    CORNER_RADIUS = 10
    BG_COLOR = "#3c3c3c"
    HOVER_BG_COLOR = "#4a4a4a"
    BORDER_COLOR = "#555555"
    TEXT_COLOR = "#ffffff"

    def __init__(
        self,
        placeholder_text: str,
        file_filter: str,
        box_size: QSize,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(placeholder_text, parent)
        self._file_filter = file_filter
        self._placeholder_text = placeholder_text
        self._pixmap: QPixmap | None = None

        self.setFixedSize(box_size)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {self.BG_COLOR};
                color: {self.TEXT_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: {self.CORNER_RADIUS}px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {self.HOVER_BG_COLOR};
            }}
            """
        )
        self.clicked.connect(self._browse_for_image)

    def _browse_for_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select image", "", self._file_filter
        )
        if not file_path:
            return

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return

        self._pixmap = pixmap
        self.setText("")
        self.update()
        self.image_selected.emit(file_path)

    def reset_placeholder(self, placeholder_text: str) -> None:
        self._placeholder_text = placeholder_text
        self._pixmap = None
        self.setIcon(QIcon())
        self.setText(placeholder_text)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._pixmap is None or self._pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(0, 0, self.width(), self.height())

        background_color = QColor(
            self.HOVER_BG_COLOR if self.underMouse() else self.BG_COLOR
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(background_color)
        painter.drawRoundedRect(rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.save()
        painter.setClipPath(clip_path)

        scaled = self._pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        x_offset = (scaled.width() - self.width()) // 2
        y_offset = (scaled.height() - self.height()) // 2
        painter.drawPixmap(-x_offset, -y_offset, scaled)

        painter.restore()

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(self.BORDER_COLOR), 1))
        border_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(border_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)


class ShortcutsPage(QWidget):
    """Page 1: intro (title / description / github link) on the left,
    the list of discovered shortcuts.vdf files on the right, a manual
    browse row, and a full-width Next button at the bottom."""

    next_requested = Signal(str)  # emits the confirmed shortcuts.vdf path

    INTRO_WIDTH    = 240
    ACCOUNTS_WIDTH = TOTAL_ROW_WIDTH - INTRO_WIDTH - ROW_SPACING

    def __init__(
        self,
        existing_vdfs: list[str],
        user_dirs: list[Path],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.file_path = ""
        self._existing = existing_vdfs
        self._user_dirs = user_dirs

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 40)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignTop)

        # --- intro (left) + shortcuts.vdf list (right) ----------------
        top_row = QHBoxLayout()
        top_row.setSpacing(ROW_SPACING)

        intro_widget = QWidget()
        intro_widget.setFixedWidth(self.INTRO_WIDTH)
        intro_layout = QVBoxLayout(intro_widget)
        intro_layout.setContentsMargins(0, 0, 0, 0)
        intro_layout.setSpacing(10)

        title_label = QLabel("Non Steam Emulation")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setWordWrap(True)

        subtitle_label = QLabel("A tool that makes adding emulated games to steam easier")
        subtitle_label.setWordWrap(True)

        link_label = QLabel(f'<a href="{GITHUB_URL}">{GITHUB_URL}</a>')
        link_label.setOpenExternalLinks(True)
        link_label.setWordWrap(True)

        for widget in (title_label, subtitle_label, link_label):
            intro_layout.addWidget(widget)
        intro_layout.addStretch(1)

        accounts_widget = QWidget()
        accounts_widget.setFixedWidth(self.ACCOUNTS_WIDTH)
        accounts_layout = QVBoxLayout(accounts_widget)
        accounts_layout.setContentsMargins(0, 0, 0, 0)
        accounts_layout.setSpacing(8)

        self._list_title_label = QLabel()
        list_title_font = QFont()
        list_title_font.setBold(True)
        self._list_title_label.setFont(list_title_font)
        self._list_title_label.setWordWrap(True)
        accounts_layout.addWidget(self._list_title_label)

        self._list_sub_label = QLabel()
        self._list_sub_label.setWordWrap(True)
        accounts_layout.addWidget(self._list_sub_label)

        self._btn_area = QVBoxLayout()
        self._btn_area.setSpacing(6)
        accounts_layout.addLayout(self._btn_area)
        accounts_layout.addStretch(1)

        top_row.addWidget(intro_widget)
        top_row.addWidget(accounts_widget)
        root.addStretch(3)
        root.addLayout(top_row)

        root.addStretch(1)

        # --- status line (replaces pop-ups) ------------------------------
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        # --- manual browse row, kept just in case -------------------------
        browse_container = QWidget()
        browse_container.setFixedWidth(TOTAL_ROW_WIDTH)
        browse_row = QHBoxLayout(browse_container)
        browse_row.setContentsMargins(0, 0, 0, 0)
        browse_row.setSpacing(ROW_SPACING)
        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("or browse for shortcuts.vdf manually...")
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(BROWSE_BUTTON_WIDTH)
        style_primary(browse_btn)
        browse_btn.clicked.connect(self._browse)
        browse_row.addWidget(self._path_edit)
        browse_row.addWidget(browse_btn)
        root.addWidget(browse_container, alignment=Qt.AlignHCenter)

        # --- Next button, full width ---------------------------------
        self.next_button = QPushButton("Next")
        self.next_button.setFixedWidth(TOTAL_ROW_WIDTH)
        self.next_button.setEnabled(False)
        style_primary(self.next_button)
        self.next_button.clicked.connect(self._on_next_clicked)
        root.addWidget(self.next_button, alignment=Qt.AlignHCenter)

        self._populate()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_btn_area(self) -> None:
        while self._btn_area.count():
            item = self._btn_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _set_status(self, text: str, color: str = "#5dade2") -> None:
        self._status_label.setStyleSheet(f"color: {color};")
        self._status_label.setText(text)

    def _confirm(self, path: str) -> None:
        """Called when a final file path is chosen (by button or browse)."""
        self.file_path = path
        self._path_edit.setText(path)
        self.next_button.setEnabled(True)
        self._set_status(f"\u2713  {path}", color="#2ecc71")

    def show_error(self, text: str) -> None:
        """Called by the controller when the confirmed file turns out to
        be invalid; keeps the user on this page instead of a pop-up."""
        self.file_path = ""
        self.next_button.setEnabled(False)
        self._set_status(text, color="#e74c3c")

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        self._clear_btn_area()

        if not self._user_dirs:
            # ── Case: Steam userdata folder not found ────────────────────
            self._list_title_label.setText("Steam userdata folder not found")
            self._list_sub_label.setText(
                "Browse for an existing shortcuts.vdf manually:\n"
                "(Steam\\userdata\\<SteamID>\\config\\shortcuts.vdf)"
            )
            return

        existing_set = set(self._existing)  # for O(1) lookup

        if len(self._user_dirs) == 1:
            udir = self._user_dirs[0]
            vdf_path = str(udir / "config" / "shortcuts.vdf")
            if vdf_path in existing_set:
                # ── Single user, already has vdf ─────────────────────────
                self._list_title_label.setText("shortcuts.vdf found")
                self._list_sub_label.setText(
                    f"Found shortcuts.vdf for Steam ID {udir.name}."
                )
                self._confirm(vdf_path)
            else:
                # ── Single user, no vdf → auto-create silently ───────────
                self._list_title_label.setText("No shortcuts.vdf found")
                self._list_sub_label.setText(
                    f"Creating shortcuts.vdf for Steam ID {udir.name}..."
                )
                try:
                    create_empty_shortcuts_vdf(vdf_path)
                    self._confirm(vdf_path)
                    self._list_sub_label.setText(
                        f"shortcuts.vdf created for Steam ID {udir.name}."
                    )
                except Exception as exc:
                    self._set_status(f"Error: {exc}", color="#e74c3c")
            return

        # ── Multiple user dirs: always show all of them ──────────────────
        has_any_vdf = bool(self._existing)
        if has_any_vdf:
            self._list_title_label.setText("Select a Steam account")
            self._list_sub_label.setText(
                "\u2713 = has shortcuts.vdf,  \u2717 = will be created"
            )
        else:
            self._list_title_label.setText("No shortcuts.vdf found")
            self._list_sub_label.setText(
                "Choose which account to create shortcuts.vdf for:"
            )

        for udir in self._user_dirs:
            steam_id  = udir.name
            vdf_path  = str(udir / "config" / "shortcuts.vdf")
            has_vdf   = vdf_path in existing_set
            marker    = "\u2713 has vdf" if has_vdf else "\u2717 no vdf"
            label     = f"Steam ID {steam_id}   |   {marker}"
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            if has_vdf:
                captured_path = vdf_path
                btn.clicked.connect(
                    lambda checked=False, p=captured_path: self._select_existing(p)
                )
            else:
                captured_dir = udir
                btn.clicked.connect(
                    lambda checked=False, d=captured_dir: self._create_for(d)
                )
            self._btn_area.addWidget(btn)

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def _create_for(self, user_dir: Path) -> None:
        target = str(user_dir / "config" / "shortcuts.vdf")
        try:
            create_empty_shortcuts_vdf(target)
            self._confirm(target)
            self._list_sub_label.setText(
                f"shortcuts.vdf created for Steam ID {user_dir.name}."
            )
        except Exception as exc:
            self._set_status(f"Error: {exc}", color="#e74c3c")

    def _select_existing(self, vdf_path: str) -> None:
        """Use an existing shortcuts.vdf chosen via an account button.

        Account buttons are left enabled (not locked/greyed out) so the
        user can freely change their pick, including after going Back
        from a later page.
        """
        self._confirm(vdf_path)

    def _browse(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select shortcuts.vdf", "", "VDF files (*.vdf)"
        )
        if file_path:
            self._confirm(file_path)

    def _on_next_clicked(self) -> None:
        if self.file_path:
            self.next_requested.emit(self.file_path)


class GameInfoWindow(QWidget):
    """Page 2: back / game name / emulator path / game path / Next."""

    back_requested = Signal()
    next_requested = Signal()

    def __init__(self, entry: GameEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(WINDOW_TITLE)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(40, 40, 40, 40)
        root_layout.setSpacing(24)
        root_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.back_button = QPushButton("Back")
        self.back_button.setFixedWidth(TOTAL_ROW_WIDTH)
        style_primary(self.back_button)
        self.back_button.clicked.connect(self.back_requested.emit)
        root_layout.addWidget(self.back_button, alignment=Qt.AlignHCenter)

        root_layout.addStretch(1)

        self.game_name_edit = QLineEdit()
        self.game_name_edit.setPlaceholderText("Enter game name here...")
        self.game_name_edit.setFixedWidth(NAME_FIELD_WIDTH)
        # Blue border marks this as the one field you actually type into.
        self.game_name_edit.setStyleSheet(
            f"QLineEdit {{ border: 2px solid {ACCENT_BLUE}; border-radius: 4px; padding: 3px 6px; }}"
        )
        self.game_name_edit.textChanged.connect(self._update_next_button_state)
        root_layout.addLayout(self._labeled_row("Game Name :", self.game_name_edit))

        self.emulator_path_edit = QLineEdit()
        self.emulator_path_edit.setReadOnly(True)
        self.emulator_path_edit.setPlaceholderText("No emulator selected...")
        self.emulator_path_edit.textChanged.connect(self._update_next_button_state)
        emulator_browse_button = QPushButton("browse")
        style_primary(emulator_browse_button)
        emulator_browse_button.clicked.connect(self._browse_emulator_path)
        root_layout.addLayout(
            self._labeled_row("Emulator path", self.emulator_path_edit, emulator_browse_button)
        )

        self.game_path_edit = QLineEdit()
        self.game_path_edit.setReadOnly(True)
        self.game_path_edit.setPlaceholderText("No game selected...")
        game_browse_button = QPushButton("browse")
        style_primary(game_browse_button)
        game_browse_button.clicked.connect(self._browse_game_path)
        root_layout.addLayout(
            self._labeled_row("Game path", self.game_path_edit, game_browse_button)
        )

        root_layout.addStretch(1)

        self.next_button = QPushButton("Next")
        self.next_button.setFixedWidth(TOTAL_ROW_WIDTH)
        self.next_button.setEnabled(False)
        style_primary(self.next_button)
        self.next_button.clicked.connect(self._on_next_clicked)
        root_layout.addWidget(self.next_button, alignment=Qt.AlignHCenter)

    def _labeled_row(
        self,
        label_text: str,
        line_edit: QLineEdit,
        browse_button: QPushButton | None = None,
    ) -> QHBoxLayout:
        row_layout = QHBoxLayout()
        row_layout.setSpacing(ROW_SPACING)
        label = QLabel(label_text)
        label.setFixedWidth(LABEL_WIDTH)
        row_layout.addWidget(label)
        row_layout.addWidget(line_edit)
        if browse_button is not None:
            line_edit.setFixedWidth(PATH_FIELD_WIDTH)
            browse_button.setFixedWidth(BROWSE_BUTTON_WIDTH)
            row_layout.addWidget(browse_button)
        return row_layout

    def _browse_emulator_path(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select emulator executable", "", EXE_FILE_FILTER
        )
        if file_path:
            self.emulator_path_edit.setText(file_path)

    def _browse_game_path(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select game file", "", ANY_FILE_FILTER
        )
        if file_path:
            self.game_path_edit.setText(file_path)

    def _update_next_button_state(self) -> None:
        has_emulator_path = bool(self.emulator_path_edit.text())
        has_game_name = bool(self.game_name_edit.text().strip())
        self.next_button.setEnabled(has_emulator_path and has_game_name)

    def _on_next_clicked(self) -> None:
        self.entry.game_name = self.game_name_edit.text()
        self.entry.emulator_path = self.emulator_path_edit.text()
        self.entry.game_path = self.game_path_edit.text()
        self.next_requested.emit()

    def load_from_entry(self) -> None:
        self.game_name_edit.setText(self.entry.game_name)
        self.emulator_path_edit.setText(self.entry.emulator_path)
        self.game_path_edit.setText(self.entry.game_path)


class ArtworkWindow(QWidget):
    """Page 3: back / icon / grid / hero / logo / preview / Add.

    Left untouched, exactly as it was before the overhaul.
    """

    back_requested = Signal()
    add_requested  = Signal()

    LEFT_COLUMN_WIDTH   = 160
    MIDDLE_COLUMN_WIDTH = LEFT_COLUMN_WIDTH  # kept equal so grid/logo/icon share the same width
    RIGHT_COLUMN_WIDTH = 210
    GRID_SPACING = 14

    BACK_BUTTON_HEIGHT = 36
    ICON_SIZE = 100

    HERO_HEIGHT = 150
    SMALL_BUTTON_HEIGHT = 56
    ADD_BUTTON_HEIGHT = SMALL_BUTTON_HEIGHT * 2
    BOTTOM_SECTION_HEIGHT = (
        SMALL_BUTTON_HEIGHT * 2 + ADD_BUTTON_HEIGHT + GRID_SPACING * 2
    )
    HERO_WIDTH = MIDDLE_COLUMN_WIDTH + GRID_SPACING + RIGHT_COLUMN_WIDTH
    TOTAL_CONTENT_HEIGHT = HERO_HEIGHT + GRID_SPACING + BOTTOM_SECTION_HEIGHT
    GRID_HEIGHT = TOTAL_CONTENT_HEIGHT - BACK_BUTTON_HEIGHT - ICON_SIZE - GRID_SPACING * 2
    SPLIT_BUTTON_HEIGHT = (BOTTOM_SECTION_HEIGHT - GRID_SPACING) // 2

    def __init__(self, entry: GameEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(WINDOW_TITLE)

        grid_layout = QGridLayout(self)
        grid_layout.setContentsMargins(24, 24, 24, 24)
        grid_layout.setHorizontalSpacing(self.GRID_SPACING)
        grid_layout.setVerticalSpacing(self.GRID_SPACING)
        grid_layout.setColumnMinimumWidth(0, self.LEFT_COLUMN_WIDTH)
        grid_layout.setColumnMinimumWidth(1, self.MIDDLE_COLUMN_WIDTH)
        grid_layout.setColumnMinimumWidth(2, self.RIGHT_COLUMN_WIDTH)
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 0)
        grid_layout.setColumnStretch(2, 0)

        left_column_widget = QWidget()
        left_column_widget.setFixedWidth(self.LEFT_COLUMN_WIDTH)
        left_column_layout = QVBoxLayout(left_column_widget)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(self.GRID_SPACING)

        self.back_button = QPushButton("back")
        self.back_button.setFixedSize(self.LEFT_COLUMN_WIDTH, self.BACK_BUTTON_HEIGHT)
        style_primary(self.back_button)
        self.back_button.clicked.connect(self.back_requested.emit)
        left_column_layout.addWidget(self.back_button)

        self.icon_button = ImagePickerButton(
            placeholder_text="browse icon",
            file_filter=ICON_FILE_FILTER,
            box_size=QSize(self.LEFT_COLUMN_WIDTH, self.ICON_SIZE),
        )
        self.icon_button.image_selected.connect(self._on_icon_selected)
        left_column_layout.addWidget(self.icon_button)

        self.grid_button = ImagePickerButton(
            placeholder_text="browse grid",
            file_filter=ARTWORK_FILE_FILTER,
            box_size=QSize(self.LEFT_COLUMN_WIDTH, self.GRID_HEIGHT),
        )
        self.grid_button.image_selected.connect(self._on_grid_selected)
        left_column_layout.addWidget(self.grid_button)

        grid_layout.addWidget(left_column_widget, 0, 0, 4, 1)

        self.hero_button = ImagePickerButton(
            placeholder_text="browse hero",
            file_filter=ARTWORK_FILE_FILTER,
            box_size=QSize(self.HERO_WIDTH, self.HERO_HEIGHT),
        )
        self.hero_button.image_selected.connect(self._on_hero_selected)
        grid_layout.addWidget(self.hero_button, 0, 1, 1, 2)

        middle_column_widget = QWidget()
        middle_column_widget.setFixedWidth(self.MIDDLE_COLUMN_WIDTH)
        middle_column_layout = QVBoxLayout(middle_column_widget)
        middle_column_layout.setContentsMargins(0, 0, 0, 0)
        middle_column_layout.setSpacing(self.GRID_SPACING)

        self.logo_button = ImagePickerButton(
            placeholder_text="browse logo",
            file_filter=ARTWORK_FILE_FILTER,
            box_size=QSize(self.MIDDLE_COLUMN_WIDTH, self.SPLIT_BUTTON_HEIGHT),
        )
        self.logo_button.image_selected.connect(self._on_logo_selected)
        middle_column_layout.addWidget(self.logo_button)

        self.preview_button = ImagePickerButton(
            placeholder_text="browse preview",
            file_filter=ARTWORK_FILE_FILTER,
            box_size=QSize(self.MIDDLE_COLUMN_WIDTH, self.SPLIT_BUTTON_HEIGHT),
        )
        self.preview_button.image_selected.connect(self._on_preview_selected)
        middle_column_layout.addWidget(self.preview_button)

        grid_layout.addWidget(middle_column_widget, 1, 1, 3, 1)


        self.open_grid_directory_button = QPushButton("open grid directory")
        self.open_grid_directory_button.setFixedSize(
            self.RIGHT_COLUMN_WIDTH, self.SMALL_BUTTON_HEIGHT
        )
        self.open_grid_directory_button.clicked.connect(self._open_grid_directory)
        grid_layout.addWidget(self.open_grid_directory_button, 1, 2)

        self.open_shortcuts_directory_button = QPushButton("open shortcuts.vdf directory")
        self.open_shortcuts_directory_button.setFixedSize(
            self.RIGHT_COLUMN_WIDTH, self.SMALL_BUTTON_HEIGHT
        )
        self.open_shortcuts_directory_button.clicked.connect(self._open_shortcuts_directory)
        grid_layout.addWidget(self.open_shortcuts_directory_button, 2, 2)

        self.add_button = QPushButton("Add")
        self.add_button.setFixedSize(self.RIGHT_COLUMN_WIDTH, self.ADD_BUTTON_HEIGHT)
        style_primary(self.add_button, radius=8)
        self.add_button.clicked.connect(self.add_requested.emit)
        grid_layout.addWidget(self.add_button, 3, 2)

    def _on_icon_selected(self, file_path: str) -> None:
        self.entry.icon_path = file_path

    def _on_hero_selected(self, file_path: str) -> None:
        self.entry.hero_path = file_path

    def _on_grid_selected(self, file_path: str) -> None:
        self.entry.grid_path = file_path

    def _on_logo_selected(self, file_path: str) -> None:
        self.entry.logo_path = file_path

    def _on_preview_selected(self, file_path: str) -> None:
        self.entry.preview_path = file_path

    def _open_grid_directory(self) -> None:
        ######################################


        os.startfile(STEAM_GRID_DIRECTORY)


        ######################################

    def _open_shortcuts_directory(self) -> None:
        ######################################


        os.startfile(STEAM_SHORTCUTS_DIRECTORY)


        ######################################

    def reset_images(self) -> None:
        self.icon_button.reset_placeholder("icon")
        self.hero_button.reset_placeholder("hero")
        self.grid_button.reset_placeholder("grid")
        self.logo_button.reset_placeholder("logo")
        self.preview_button.reset_placeholder("preview")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.parent() is None:  # skip when embedded in QStackedWidget
            fit_and_center(self)


class DonePage(QWidget):
    """Page 4: "Game Added!" / backup path / add another, restart, quit."""

    add_another_requested = Signal()
    restart_requested      = Signal()
    quit_requested          = Signal()

    ACTION_BUTTON_SIZE = 90

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignCenter)

        root.addStretch(1)

        done_label = QLabel("Game Added!")
        done_font = QFont()
        done_font.setPointSize(24)
        done_font.setBold(True)
        done_label.setFont(done_font)
        done_label.setAlignment(Qt.AlignCenter)
        root.addWidget(done_label)

        self._backup_label = QLabel("")
        self._backup_label.setAlignment(Qt.AlignCenter)
        self._backup_label.setWordWrap(True)
        self._backup_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._backup_label)

        warning_label = QLabel("!!! restart Steam for changes to take effect !!!")
        warning_label.setStyleSheet("color: red; font-weight: bold;")
        warning_label.setAlignment(Qt.AlignCenter)
        warning_label.setWordWrap(True)
        root.addWidget(warning_label)

        root.addSpacing(20)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(30)
        buttons_row.addStretch(1)
        buttons_row.addLayout(
            self._build_action_column("+", "Add another", self.add_another_requested.emit)
        )
        buttons_row.addLayout(
            self._build_action_column("\u21bb", "Restart Steam", self.restart_requested.emit)
        )
        buttons_row.addLayout(
            self._build_action_column("\u2715", "Quit", self.quit_requested.emit)
        )
        buttons_row.addStretch(1)
        root.addLayout(buttons_row)

        root.addStretch(1)

    def _build_action_column(self, symbol: str, caption_text: str, callback) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(8)
        column.setAlignment(Qt.AlignHCenter)

        button = QPushButton(symbol)
        button.setFixedSize(self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE)
        symbol_font = QFont()
        symbol_font.setPointSize(26)
        symbol_font.setBold(True)
        button.setFont(symbol_font)
        style_primary(button, radius=16)
        button.clicked.connect(callback)
        column.addWidget(button, alignment=Qt.AlignHCenter)

        caption = QLabel(caption_text)
        caption.setAlignment(Qt.AlignCenter)
        column.addWidget(caption, alignment=Qt.AlignHCenter)

        return column

    def set_backup_path(self, directory: str) -> None:
        self._backup_label.setText(f"Backup of shortcuts.vdf saved in:\n{directory}")


class WizardController:
    PAGE_SHORTCUTS = 0
    PAGE_GAME_INFO = 1
    PAGE_ARTWORK   = 2
    PAGE_DONE      = 3

    def __init__(self, existing_vdfs: list[str], user_dirs: list[Path]) -> None:
        self.entry = GameEntry()

        self.shortcuts_page   = ShortcutsPage(existing_vdfs, user_dirs)
        self.game_info_window = GameInfoWindow(self.entry)
        self.artwork_window   = ArtworkWindow(self.entry)
        self.done_page        = DonePage()

        # Silently skip straight past the picker when there's exactly one
        # unambiguous Steam account to use (same shortcut the old startup
        # flow took) - the page is still built underneath in case the user
        # hits "Back" and wants to change their mind.
        self._auto_confirm_path: str | None = None
        if len(existing_vdfs) == 1 and len(user_dirs) == 1:
            self._auto_confirm_path = existing_vdfs[0]

        self._host = QWidget()
        self._host.setWindowTitle(WINDOW_TITLE)
        host_layout = QVBoxLayout(self._host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.shortcuts_page)    # PAGE_SHORTCUTS = 0
        self._stack.addWidget(self.game_info_window)  # PAGE_GAME_INFO = 1
        self._stack.addWidget(self.artwork_window)    # PAGE_ARTWORK   = 2
        self._stack.addWidget(self.done_page)          # PAGE_DONE      = 3
        host_layout.addWidget(self._stack)

        # Size every page to match ArtworkWindow so the window never resizes
        # or pops in and out - it's one window from start to finish.
        self.artwork_window.layout().activate()
        artwork_size = self.artwork_window.sizeHint()
        self._host.setFixedSize(artwork_size)

        self.shortcuts_page.next_requested.connect(self._on_shortcuts_confirmed)

        self.game_info_window.back_requested.connect(self._go_to_shortcuts)
        self.game_info_window.next_requested.connect(self._go_to_artwork)

        self.artwork_window.back_requested.connect(self._go_to_game_info)
        self.artwork_window.add_requested.connect(self._on_add_clicked)

        self.done_page.add_another_requested.connect(self._on_add_another)
        self.done_page.restart_requested.connect(self._on_restart)
        self.done_page.quit_requested.connect(QApplication.instance().quit)

    def start(self) -> None:
        if self._auto_confirm_path:
            self._on_shortcuts_confirmed(self._auto_confirm_path)

        screen = QApplication.primaryScreen()
        if screen is not None:
            ag = screen.availableGeometry()
            self._host.move(
                ag.center().x() - self._host.width()  // 2,
                ag.center().y() - self._host.height() // 2,
            )
        self._host.show()

    def _go_to_shortcuts(self) -> None:
        self._stack.setCurrentIndex(self.PAGE_SHORTCUTS)

    def _go_to_artwork(self) -> None:
        self._stack.setCurrentIndex(self.PAGE_ARTWORK)

    def _go_to_game_info(self) -> None:
        self._stack.setCurrentIndex(self.PAGE_GAME_INFO)

    def _on_shortcuts_confirmed(self, chosen_path: str) -> None:
        # Normalise path separators
        chosen_path = chosen_path.replace("/", "\\")

        if not chosen_path or not os.path.isfile(chosen_path):
            self.shortcuts_page.show_error("Selected file no longer exists.")
            return

        # Validate the chosen file
        is_valid = False
        try:
            with open(chosen_path, "rb") as f:
                root = vdf.binary_load(f)
                # Accept file as long as the 'shortcuts' key is present,
                # even when it contains zero entries (freshly-created file).
                if 'shortcuts' in root:
                    is_valid = True
        except Exception:
            pass

        if not is_valid:
            self.shortcuts_page.show_error("shortcuts.vdf is empty or cannot be read.")
            return

        global STEAM_SHORTCUTS_FILE_PATH, STEAM_SHORTCUTS_DIRECTORY, STEAM_GRID_DIRECTORY
        STEAM_SHORTCUTS_FILE_PATH = chosen_path
        STEAM_SHORTCUTS_DIRECTORY = os.path.dirname(chosen_path) + "\\"

        # Grid folder lives INSIDE the config folder: userdata/<id>/config/grid
        # Only created if it doesn't already exist.
        grid_dir = Path(chosen_path).parent / "grid"
        os.makedirs(str(grid_dir), exist_ok=True)
        STEAM_GRID_DIRECTORY = str(grid_dir)

        self._stack.setCurrentIndex(self.PAGE_GAME_INFO)

    def _on_add_clicked(self) -> None:
        # TODO: call your Main.py logic here before showing the done page.
        # All user input is in self.entry:
        #   self.entry.game_name, emulator_path, game_path
        #   self.entry.icon_path, hero_path, grid_path, logo_path, preview_path

        ####################################


        #create shortcuts.vdf backup just in case
        if os.path.exists(STEAM_SHORTCUTS_FILE_PATH):
            os.makedirs(SHORTCUTS_BACKUP_DIRECTORY, exist_ok=True)
            shutil.copy(STEAM_SHORTCUTS_FILE_PATH, SHORTCUTS_BACKUP_DIRECTORY)
            now = datetime.now()
            now = now.strftime("%Y-%m-%d-%H%M%S")
            os.rename(f"{SHORTCUTS_BACKUP_DIRECTORY}\\shortcuts.vdf", f"{SHORTCUTS_BACKUP_DIRECTORY}\\shortcuts_backup_{now}.vdf")


        #calculate appid and artid(game art)
        combined_string = (self.entry.game_name + self.entry.emulator_path + "\0")
        crc = zlib.crc32(combined_string.encode('cp1252'))
        art_id = crc | 0x80000000
        app_id = art_id
        app_id -= 0x100000000

        emulator_start_in_path = Path(self.entry.emulator_path)
        emulator_start_in_path = str(emulator_start_in_path.parent)


        # Adding Game Art
        if self.entry.grid_path and not os.path.exists(f"{STEAM_GRID_DIRECTORY}\\{art_id}p.png"):
            shutil.copy(self.entry.grid_path, STEAM_GRID_DIRECTORY)
            os.rename(f"{STEAM_GRID_DIRECTORY}\\{os.path.basename(self.entry.grid_path)}", f"{STEAM_GRID_DIRECTORY}\\{art_id}p.png")

        if self.entry.hero_path and not os.path.exists(f"{STEAM_GRID_DIRECTORY}\\{art_id}_hero.png"):
            shutil.copy(self.entry.hero_path, STEAM_GRID_DIRECTORY)
            os.rename(f"{STEAM_GRID_DIRECTORY}\\{os.path.basename(self.entry.hero_path)}", f"{STEAM_GRID_DIRECTORY}\\{art_id}_hero.png")

        if self.entry.logo_path and not os.path.exists(f"{STEAM_GRID_DIRECTORY}\\{art_id}_logo.png"):
            shutil.copy(self.entry.logo_path, STEAM_GRID_DIRECTORY)
            os.rename(f"{STEAM_GRID_DIRECTORY}\\{os.path.basename(self.entry.logo_path)}", f"{STEAM_GRID_DIRECTORY}\\{art_id}_logo.png")

        if self.entry.preview_path and not os.path.exists(f"{STEAM_GRID_DIRECTORY}\\{art_id}.png"):
            shutil.copy(self.entry.preview_path, STEAM_GRID_DIRECTORY)
            os.rename(f"{STEAM_GRID_DIRECTORY}\\{os.path.basename(self.entry.preview_path)}", f"{STEAM_GRID_DIRECTORY}\\{art_id}.png")

        #clean the game path to use backslashes instead of forward slashes for windows
        self.entry.game_path = self.entry.game_path.replace("/", "\\")

        #adding game data to the file
        new_game =  {'appid': app_id,
                    'AppName': self.entry.game_name,
                    'Exe': f"\"{self.entry.emulator_path}\" \"{self.entry.game_path}\"",
                    'StartDir': emulator_start_in_path,
                    'icon': self.entry.icon_path,
                    'ShortcutPath': '',
                    'LaunchOptions': '',
                    'IsHidden': 0,
                    'AllowDesktopConfig': 1,
                    'AllowOverlay': 1,
                    'OpenVR': 0,
                    'Devkit': 0,
                    'DevkitGameID': '',
                    'DevkitOverrideAppID': 0,
                    'LastPlayTime': 0,
                    'FlatpakAppID': '',
                    'sortas': '',
                    'tags': {}}

        with open(STEAM_SHORTCUTS_FILE_PATH, "rb") as f:
            root = vdf.binary_load(f)
            root['shortcuts'][str(len(root['shortcuts']))] = new_game
            root['shortcuts'] = root['shortcuts']

        with open(STEAM_SHORTCUTS_FILE_PATH, "wb") as f:
            vdf.binary_dump(root, f)


        ####################################

        self.done_page.set_backup_path(os.path.abspath(SHORTCUTS_BACKUP_DIRECTORY))
        self._stack.setCurrentIndex(self.PAGE_DONE)

    def _on_add_another(self) -> None:
        self.entry.reset()
        self.game_info_window.load_from_entry()
        self.artwork_window.reset_images()
        self._stack.setCurrentIndex(self.PAGE_GAME_INFO)

    def _on_restart(self) -> None:
        restart_steam()
        QApplication.instance().quit()


def main() -> None:
    app = QApplication(sys.argv)

    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    icon_path = os.path.join(base_path, "icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    # ── Discover what's already on disk ──────────────────────────────────
    existing_vdfs, user_dirs = discover_steam_state()

    controller = WizardController(existing_vdfs, user_dirs)
    controller.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()