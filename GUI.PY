"""
Non Steam Emulation - GUI (PySide6)

Screens:
    1. GameInfoWindow  - game name / emulator path / game path / Next
    2. ArtworkWindow   - back / icon / grid / hero / logo / preview / Add
    3. DonePopup       - done! / add another one / quit

"""

from __future__ import annotations

import sys
from dataclasses import dataclass

####################################


import vdf
import zlib
import shutil
from datetime import datetime
import os
from pathlib import Path


####################################

from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
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

POPUP_SIZE = QSize(450, 220)

####################################


STEAM_USERDATA = Path("C:\\Program Files (x86)\\Steam\\userdata")

for file_path in STEAM_USERDATA.rglob("shortcuts.vdf"):
    file_path = str(file_path)
    path = file_path.split("\\")
    for part in path:
        if ".vdf" in part:
            path.pop()
    shortcuts_file_path = "\\".join(path) + "\\"
STEAM_SHORTCUTS_DIRECTORY = shortcuts_file_path

for file_path in STEAM_USERDATA.rglob("grid"):
    STEAM_GRID_DIRECTORY = str(file_path)

SHORTCUTS_BACKUP_DIRECTORY = "shortcuts_file_backups"

STEAM_SHORTCUTS_FILE_PATH = f"{STEAM_SHORTCUTS_DIRECTORY}\\shortcuts.vdf"


####################################

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


class GameInfoWindow(QWidget):
    """Screen 1: app header + game name / emulator path / game path / Next."""

    next_requested = Signal()

    LABEL_WIDTH = 110
    PATH_FIELD_WIDTH = 300
    BROWSE_BUTTON_WIDTH = 70
    ROW_SPACING = 10
    NAME_FIELD_WIDTH = PATH_FIELD_WIDTH + ROW_SPACING + BROWSE_BUTTON_WIDTH
    TOTAL_ROW_WIDTH = LABEL_WIDTH + ROW_SPACING + NAME_FIELD_WIDTH

    def __init__(self, entry: GameEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(WINDOW_TITLE)
        self._forced_size: QSize | None = None  # set by WizardController

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(40, 40, 40, 40)
        root_layout.setSpacing(24)
        root_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        root_layout.addLayout(self._build_intro_section())

        self.game_name_edit = QLineEdit()
        self.game_name_edit.setPlaceholderText("Enter game name here...")
        self.game_name_edit.setFixedWidth(self.NAME_FIELD_WIDTH)
        self.game_name_edit.textChanged.connect(self._update_next_button_state)
        root_layout.addLayout(self._labeled_row("Game Name :", self.game_name_edit))

        self.emulator_path_edit = QLineEdit()
        self.emulator_path_edit.setReadOnly(True)
        self.emulator_path_edit.setPlaceholderText("No emulator selected...")
        self.emulator_path_edit.textChanged.connect(self._update_next_button_state)
        emulator_browse_button = QPushButton("browse")
        emulator_browse_button.clicked.connect(self._browse_emulator_path)
        root_layout.addLayout(
            self._labeled_row("Emulator path", self.emulator_path_edit, emulator_browse_button)
        )

        self.game_path_edit = QLineEdit()
        self.game_path_edit.setReadOnly(True)
        self.game_path_edit.setPlaceholderText("No game selected...")
        game_browse_button = QPushButton("browse")
        game_browse_button.clicked.connect(self._browse_game_path)
        root_layout.addLayout(
            self._labeled_row("Game path", self.game_path_edit, game_browse_button)
        )

        self.next_button = QPushButton("Next")
        self.next_button.setFixedWidth(self.TOTAL_ROW_WIDTH)
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self._on_next_clicked)
        root_layout.addWidget(self.next_button, alignment=Qt.AlignHCenter)

    def set_forced_size(self, size: QSize) -> None:
        self._forced_size = size
        if self.isVisible():
            fit_and_center(self, self._forced_size)

    def _build_intro_section(self) -> QVBoxLayout:
        intro_layout = QVBoxLayout()
        intro_layout.setSpacing(12)
        intro_layout.setContentsMargins(0, 0, 0, 8)
        intro_layout.setAlignment(Qt.AlignCenter)

        title_label = QLabel("Non Steam Emulation")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)

        subtitle_label = QLabel("A tool that makes adding emulated games to steam easier")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setWordWrap(True)
        subtitle_label.setFixedWidth(self.TOTAL_ROW_WIDTH)
        subtitle_label.setMinimumHeight(44)

        link_label = QLabel(f'<a href="{GITHUB_URL}">{GITHUB_URL}</a>')
        link_label.setAlignment(Qt.AlignCenter)
        link_label.setOpenExternalLinks(True)

        warning_label = QLabel("!!! make sure to quit steam first !!!")
        warning_label.setAlignment(Qt.AlignCenter)
        warning_label.setStyleSheet("color: red; font-weight: bold;")
        warning_label.setWordWrap(True)
        warning_label.setFixedWidth(self.TOTAL_ROW_WIDTH)
        warning_label.setMinimumHeight(28)

        for widget in (title_label, subtitle_label, link_label, warning_label):
            intro_layout.addWidget(widget)

        return intro_layout

    def _labeled_row(
        self,
        label_text: str,
        line_edit: QLineEdit,
        browse_button: QPushButton | None = None,
    ) -> QHBoxLayout:
        row_layout = QHBoxLayout()
        row_layout.setSpacing(self.ROW_SPACING)
        label = QLabel(label_text)
        label.setFixedWidth(self.LABEL_WIDTH)
        row_layout.addWidget(label)
        row_layout.addWidget(line_edit)
        if browse_button is not None:
            line_edit.setFixedWidth(self.PATH_FIELD_WIDTH)
            browse_button.setFixedWidth(self.BROWSE_BUTTON_WIDTH)
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

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.parent() is None:  # skip when embedded in QStackedWidget
            fit_and_center(self, self._forced_size)


class ArtworkWindow(QWidget):
    """Screen 2: back / icon / grid / hero / logo / preview / Add."""

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


class DonePopup(QDialog):
    """Screen 3: done! / add another one / quit."""

    ADD_ANOTHER = "add_another"
    QUIT = "quit"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.choice: str = self.QUIT

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        done_label = QLabel("Game Added !")
        done_font = QFont()
        done_font.setPointSize(16)
        done_font.setBold(True)
        done_label.setFont(done_font)
        done_label.setAlignment(Qt.AlignCenter)

        backup_label = QLabel(f"backup of shortcuts.vdf was made in:\n{SHORTCUTS_BACKUP_DIRECTORY}")
        backup_label.setAlignment(Qt.AlignCenter)
        backup_label.setWordWrap(True)
        backup_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        add_another_button = QPushButton("add another one")
        add_another_button.clicked.connect(self._choose_add_another)

        quit_button = QPushButton("quit")
        quit_button.clicked.connect(self._choose_quit)

        layout.addWidget(done_label)
        layout.addWidget(backup_label)
        layout.addWidget(add_another_button, alignment=Qt.AlignCenter)
        layout.addWidget(quit_button, alignment=Qt.AlignCenter)

    def _choose_add_another(self) -> None:
        self.choice = self.ADD_ANOTHER
        self.accept()

    def _choose_quit(self) -> None:
        self.choice = self.QUIT
        self.accept()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        fit_and_center(self, POPUP_SIZE)


class WizardController:
    PAGE_GAME_INFO = 0
    PAGE_ARTWORK   = 1

    def __init__(self) -> None:
        self.entry = GameEntry()

        self.game_info_window = GameInfoWindow(self.entry)
        self.artwork_window   = ArtworkWindow(self.entry)

        # Size both pages to match ArtworkWindow so the window never resizes.
        self.artwork_window.layout().activate()
        artwork_size = self.artwork_window.sizeHint()
        self.game_info_window.set_forced_size(artwork_size)

        self._host = QWidget()
        self._host.setWindowTitle(WINDOW_TITLE)
        host_layout = QVBoxLayout(self._host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.game_info_window)  # PAGE_GAME_INFO = 0
        self._stack.addWidget(self.artwork_window)    # PAGE_ARTWORK   = 1
        host_layout.addWidget(self._stack)

        self._host.setFixedSize(artwork_size)

        self.game_info_window.next_requested.connect(self._go_to_artwork)
        self.artwork_window.back_requested.connect(self._go_to_game_info)
        self.artwork_window.add_requested.connect(self._on_add_clicked)

    def start(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            ag = screen.availableGeometry()
            self._host.move(
                ag.center().x() - self._host.width()  // 2,
                ag.center().y() - self._host.height() // 2,
            )
        self._host.show()

    def _go_to_artwork(self) -> None:
        self._stack.setCurrentIndex(self.PAGE_ARTWORK)

    def _go_to_game_info(self) -> None:
        self._stack.setCurrentIndex(self.PAGE_GAME_INFO)

    def _on_add_clicked(self) -> None:
        # TODO: call your Main.py logic here before showing the popup.
        # All user input is in self.entry:
        #   self.entry.game_name, emulator_path, game_path
        #   self.entry.icon_path, hero_path, grid_path, logo_path, preview_path

        ####################################


        #create shortcuts.vdf backup just in case
        os.makedirs(SHORTCUTS_BACKUP_DIRECTORY, exist_ok=True)
        shutil.copy(f"{STEAM_SHORTCUTS_DIRECTORY}\\shortcuts.vdf", SHORTCUTS_BACKUP_DIRECTORY)
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
        
        done_popup = DonePopup(self._host)
        done_popup.exec()

        if done_popup.choice == DonePopup.ADD_ANOTHER:
            self.entry.reset()
            self.game_info_window.load_from_entry()
            self.artwork_window.reset_images()
            self._stack.setCurrentIndex(self.PAGE_GAME_INFO)
        # On "quit" the popup closes and the main window stays open.
        # Uncomment below to quit the app immediately instead:
        else:
            QApplication.instance().quit()


def main() -> None:
    app = QApplication(sys.argv)
    
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    icon_path = os.path.join(base_path, "icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    controller = WizardController()
    controller.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()