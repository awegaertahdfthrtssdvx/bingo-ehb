from __future__ import annotations

import csv
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


APP_ORGANIZATION = "BingoTools"
APP_NAME = "BingoPlayerDashboard"

BINGO_DATA_FILENAME = "current_bingo_data.csv"
TEMPLE_KPH_FILENAME = "temple_osrs_ehb.csv"
MASTER_PLAYER_DATA_FILENAME = "master_player_data.csv"

DEFAULT_MASTER_PLAYER_DATA_PATH = (
    Path("data") / "June Bingo 2026" / MASTER_PLAYER_DATA_FILENAME
)

HOME_PAGE_INDEX = 0
PLAYER_PAGE_INDEX = 1

ACCENT_COLOR = QColor("#D2A85A")
LINK_COLOR = QColor("#E0B96B")

CHART_COLORS = [
    QColor("#D2A85A"),
    QColor("#6F93B7"),
    QColor("#6FA295"),
    QColor("#8D7CAF"),
    QColor("#B8796E"),
    QColor("#8C98A8"),
]


@dataclass(frozen=True)
class Registration:
    """
    Useful fields from current_bingo_data.csv.

    The date, temp_delete_this, and buy-in columns are ignored.
    """

    player_name: str
    alt_account: str
    time_zone: str
    note: str
    play_time: str


@dataclass(frozen=True)
class StatEntry:
    name: str
    gain: float
    kills_per_hour: float | None
    calculated_ehb: float | None


class SortableItem(QTableWidgetItem):
    """Display one value while sorting by another value."""

    def __init__(
        self,
        display_text: str,
        sort_value: object,
        registration_index: int | None = None,
    ) -> None:
        super().__init__(display_text)
        self.sort_value = sort_value

        if registration_index is not None:
            self.setData(
                Qt.ItemDataRole.UserRole,
                registration_index,
            )

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableItem):
            return self.sort_value < other.sort_value

        return super().__lt__(other)


class NumericItem(SortableItem):
    def __init__(
        self,
        display_text: str,
        numeric_value: float,
    ) -> None:
        super().__init__(display_text, numeric_value)
        self.setTextAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )


class SummaryCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "—",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("summaryCard")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")

        self.value_label = QLabel(value)
        self.value_label.setObjectName("cardValue")
        self.value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
        self.value_label.setToolTip(value)


class DetailValueLabel(QLabel):
    def __init__(self) -> None:
        super().__init__("—")

        self.setObjectName("detailValue")
        self.setWordWrap(True)
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
        )
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

    def set_value(self, value: str) -> None:
        displayed = value.strip() if value.strip() else "—"
        self.setText(displayed)
        self.setToolTip(displayed)


class HorizontalEhbChart(QWidget):
    """Simple dependency-free horizontal bar chart."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.title = title
        self.data: list[tuple[str, float]] = []

        self.setMinimumHeight(250)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def set_data(
        self,
        data: list[tuple[str, float]],
    ) -> None:
        self.data = sorted(
            (
                (label, value)
                for label, value in data
                if value > 0
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:10]

        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        painter.setPen(QColor("#EEF1F5"))
        title_font = QFont(self.font())
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(16, 12, self.width() - 32, 24),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            self.title,
        )

        if not self.data:
            painter.setPen(QColor("#8893A1"))
            painter.drawText(
                self.rect().adjusted(16, 40, -16, -16),
                Qt.AlignmentFlag.AlignCenter,
                "No matched Temple KPH data",
            )
            return

        left_margin = min(
            180,
            max(120, int(self.width() * 0.32)),
        )
        right_margin = 55
        top_margin = 48
        bottom_margin = 18

        chart_width = max(
            40,
            self.width()
            - left_margin
            - right_margin
            - 20,
        )
        chart_height = max(
            40,
            self.height()
            - top_margin
            - bottom_margin,
        )

        row_height = chart_height / len(self.data)
        bar_height = max(
            8,
            min(18, row_height * 0.52),
        )
        max_value = max(value for _, value in self.data)

        label_font = QFont(self.font())
        label_font.setPointSize(9)
        painter.setFont(label_font)
        font_metrics = QFontMetrics(label_font)

        for index, (label, value) in enumerate(self.data):
            center_y = (
                top_margin
                + row_height * index
                + row_height / 2
            )

            label_rect = QRectF(
                14,
                center_y - row_height / 2,
                left_margin - 26,
                row_height,
            )

            elided_label = font_metrics.elidedText(
                label,
                Qt.TextElideMode.ElideRight,
                int(label_rect.width()),
            )

            painter.setPen(QColor("#B8C0CC"))
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter,
                elided_label,
            )

            background_rect = QRectF(
                left_margin,
                center_y - bar_height / 2,
                chart_width,
                bar_height,
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#252D38"))
            painter.drawRoundedRect(
                background_rect,
                4,
                4,
            )

            filled_width = (
                chart_width * value / max_value
                if max_value > 0
                else 0
            )

            filled_rect = QRectF(
                left_margin,
                center_y - bar_height / 2,
                filled_width,
                bar_height,
            )

            painter.setBrush(ACCENT_COLOR)
            painter.drawRoundedRect(
                filled_rect,
                4,
                4,
            )

            painter.setPen(QColor("#D9DEE6"))
            painter.drawText(
                QRectF(
                    left_margin + chart_width + 8,
                    center_y - row_height / 2,
                    right_margin - 8,
                    row_height,
                ),
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter,
                format_number(value, 2),
            )


class DonutEhbChart(QWidget):
    """Simple dependency-free EHB-share donut chart."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.title = title
        self.data: list[tuple[str, float]] = []

        self.setMinimumHeight(250)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def set_data(
        self,
        data: list[tuple[str, float]],
    ) -> None:
        ordered = sorted(
            (
                (label, value)
                for label, value in data
                if value > 0
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        top = ordered[:5]
        other_total = sum(
            value for _, value in ordered[5:]
        )

        if other_total > 0:
            top.append(("Other", other_total))

        self.data = top
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        painter.setPen(QColor("#EEF1F5"))
        title_font = QFont(self.font())
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(16, 12, self.width() - 32, 24),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            self.title,
        )

        total = sum(value for _, value in self.data)

        if not self.data or total <= 0:
            painter.setPen(QColor("#8893A1"))
            painter.drawText(
                self.rect().adjusted(16, 40, -16, -16),
                Qt.AlignmentFlag.AlignCenter,
                "No matched Temple KPH data",
            )
            return

        available_height = self.height() - 68
        donut_size = min(
            max(130, int(self.width() * 0.42)),
            available_height,
            210,
        )

        donut_rect = QRectF(
            18,
            48
            + max(
                0,
                (available_height - donut_size) / 2,
            ),
            donut_size,
            donut_size,
        )

        start_angle = 90 * 16

        painter.setPen(Qt.PenStyle.NoPen)

        for index, (_label, value) in enumerate(self.data):
            span_angle = -int(
                360 * 16 * value / total
            )

            painter.setBrush(
                CHART_COLORS[
                    index % len(CHART_COLORS)
                ]
            )
            painter.drawPie(
                donut_rect,
                start_angle,
                span_angle,
            )

            start_angle += span_angle

        hole_size = donut_size * 0.56
        hole_rect = QRectF(
            donut_rect.center().x()
            - hole_size / 2,
            donut_rect.center().y()
            - hole_size / 2,
            hole_size,
            hole_size,
        )

        painter.setBrush(QColor("#171D25"))
        painter.drawEllipse(hole_rect)

        painter.setPen(QColor("#F0F2F5"))
        total_font = QFont(self.font())
        total_font.setPointSize(14)
        total_font.setBold(True)
        painter.setFont(total_font)
        painter.drawText(
            hole_rect,
            Qt.AlignmentFlag.AlignCenter,
            format_number(total, 2),
        )

        painter.setPen(QColor("#8F99A7"))
        small_font = QFont(self.font())
        small_font.setPointSize(8)
        painter.setFont(small_font)
        painter.drawText(
            QRectF(
                hole_rect.left(),
                hole_rect.center().y() + 14,
                hole_rect.width(),
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "calculated EHB",
        )

        legend_left = donut_rect.right() + 24
        legend_width = max(
            90,
            self.width() - legend_left - 14,
        )
        legend_top = 52
        legend_row_height = min(
            31,
            max(23, (self.height() - 70) / len(self.data)),
        )

        legend_font = QFont(self.font())
        legend_font.setPointSize(9)
        painter.setFont(legend_font)
        metrics = QFontMetrics(legend_font)

        for index, (label, value) in enumerate(self.data):
            row_y = legend_top + index * legend_row_height

            painter.setBrush(
                CHART_COLORS[
                    index % len(CHART_COLORS)
                ]
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                QRectF(
                    legend_left,
                    row_y + 5,
                    10,
                    10,
                ),
                2,
                2,
            )

            percentage = value / total * 100
            value_text = (
                f"{format_number(value, 2)} "
                f"({percentage:.1f}%)"
            )

            value_width = metrics.horizontalAdvance(
                value_text
            )

            label_width = max(
                40,
                int(
                    legend_width
                    - value_width
                    - 28
                ),
            )

            painter.setPen(QColor("#C7CDD6"))
            painter.drawText(
                QRectF(
                    legend_left + 18,
                    row_y,
                    label_width,
                    22,
                ),
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(
                    label,
                    Qt.TextElideMode.ElideRight,
                    label_width,
                ),
            )

            painter.setPen(QColor("#929CAB"))
            painter.drawText(
                QRectF(
                    legend_left
                    + 20
                    + label_width,
                    row_y,
                    value_width,
                    22,
                ),
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter,
                value_text,
            )


def normalize_account_name(value: str) -> str:
    """Match player names case-insensitively with underscores as spaces."""
    value = value.replace("_", " ")
    return " ".join(value.strip().casefold().split())


def normalize_activity_name(value: str) -> str:
    """
    Match activity names case-insensitively while treating underscores
    as spaces and ignoring other punctuation or repeated whitespace.
    """
    value = value.casefold().strip()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def format_number(
    value: float,
    decimal_places: int = 3,
) -> str:
    if not math.isfinite(value):
        return str(value)

    rounded_integer = round(value)

    if math.isclose(
        value,
        rounded_integer,
        abs_tol=1e-9,
    ):
        return f"{rounded_integer:,}"

    return (
        f"{value:,.{decimal_places}f}"
        .rstrip("0")
        .rstrip(".")
    )


def play_time_sort_key(
    value: str,
) -> tuple[float, float, str]:
    """
    Extract the numeric portion from values such as:
        15-20 EHB
        20-25 EHB
        35+
        35+ EHB
    """
    text = value.strip().casefold()
    numbers = re.findall(
        r"\d+(?:\.\d+)?",
        text,
    )

    if len(numbers) >= 2:
        return (
            float(numbers[0]),
            float(numbers[1]),
            text,
        )

    if len(numbers) == 1:
        lower = float(numbers[0])

        if "+" in text:
            return (lower, math.inf, text)

        return (lower, lower, text)

    return (math.inf, math.inf, text)


class BingoDashboard(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.settings = QSettings(
            APP_ORGANIZATION,
            APP_NAME,
        )

        self.master_data_path: Path | None = None
        self.bingo_data_path: Path | None = None
        self.temple_kph_path: Path | None = None

        self.registrations: list[Registration] = []
        self.temple_kph: dict[str, float] = {}

        # Keys are normalized player names. Underscores and spaces match.
        self.player_stats: dict[str, list[StatEntry]] = {}
        self.player_display_names: dict[str, str] = {}
        self.calculated_ehb_by_player: dict[
            str,
            float | None,
        ] = {}

        self.master_skipped_rows = 0
        self.current_entries: list[StatEntry] = []

        self.setWindowTitle("June Bingo 2026")
        self.resize(1200, 860)
        self.setMinimumSize(900, 680)

        self.build_ui()
        self.apply_style()

        self.load_project_data()
        self.restore_master_data_file()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("appRoot")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self.build_top_bar())

        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_home_page())
        self.pages.addWidget(self.build_player_page())

        root_layout.addWidget(self.pages, 1)

        self.statusBar().showMessage(
            "Loading bingo data…"
        )

    def build_top_bar(self) -> QWidget:
        top_bar = QFrame()
        top_bar.setObjectName("topBar")

        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(26, 14, 26, 14)
        layout.setSpacing(10)

        brand = QLabel("JUNE BINGO 2026")
        brand.setObjectName("brandLabel")

        self.home_button = QPushButton("Roster")
        self.home_button.setObjectName("navButton")
        self.home_button.clicked.connect(
            self.show_home_page
        )

        self.player_button = QPushButton(
            "Player details"
        )
        self.player_button.setObjectName("navButton")
        self.player_button.clicked.connect(
            self.show_player_page
        )

        self.folder_button = QPushButton(
            "Choose master data file"
        )
        self.folder_button.setObjectName(
            "secondaryButton"
        )
        self.folder_button.clicked.connect(
            self.select_master_data_file
        )

        layout.addWidget(brand)
        layout.addSpacing(16)
        layout.addWidget(self.home_button)
        layout.addWidget(self.player_button)
        layout.addStretch(1)
        layout.addWidget(self.folder_button)

        return top_bar

    def build_home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 28)
        layout.setSpacing(18)

        title_row = QHBoxLayout()

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("Player roster")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Sort by play time or calculated EHB, then click "
            "a player to open their detailed results."
        )
        subtitle.setObjectName("pageSubtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.home_source_label = QLabel(
            f"{BINGO_DATA_FILENAME}: not found"
        )
        self.home_source_label.setObjectName(
            "mutedLabel"
        )
        self.home_source_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        title_row.addLayout(title_box)
        title_row.addStretch(1)
        title_row.addWidget(self.home_source_label)

        layout.addLayout(title_row)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.home_search_edit = QLineEdit()
        self.home_search_edit.setPlaceholderText(
            "Search player, alt, time zone, note, or play time…"
        )
        self.home_search_edit.setClearButtonEnabled(
            True
        )
        self.home_search_edit.textChanged.connect(
            self.filter_home_table
        )

        self.refresh_button = QPushButton(
            "Refresh data"
        )
        self.refresh_button.setObjectName(
            "secondaryButton"
        )
        self.refresh_button.clicked.connect(
            self.refresh_all_data
        )

        self.view_selected_button = QPushButton(
            "View selected player"
        )
        self.view_selected_button.clicked.connect(
            self.open_selected_home_player
        )

        controls.addWidget(
            self.home_search_edit,
            1,
        )
        controls.addWidget(self.refresh_button)
        controls.addWidget(
            self.view_selected_button
        )

        layout.addLayout(controls)

        self.home_table = QTableWidget(0, 6)
        self.home_table.setHorizontalHeaderLabels(
            [
                "Player",
                "Alt account",
                "Time zone",
                "Note / preference",
                "Play time",
                "Calculated EHB",
            ]
        )
        self.configure_table(self.home_table)

        self.home_table.cellClicked.connect(
            self.home_table_cell_clicked
        )
        self.home_table.cellDoubleClicked.connect(
            self.home_table_cell_double_clicked
        )

        header = self.home_table.horizontalHeader()
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            4,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            5,
            QHeaderView.ResizeMode.ResizeToContents,
        )

        layout.addWidget(self.home_table, 1)

        hint = QLabel(
            "Calculated EHB is the sum of gain ÷ Temple kills-per-hour. "
            "The Ehb and Collections rows in master_player_data.csv are ignored."
        )
        hint.setObjectName("mutedLabel")

        layout.addWidget(hint)

        return page

    def build_player_page(self) -> QWidget:
        scroll_area = QScrollArea()
        scroll_area.setObjectName("playerScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        page = QWidget()
        page.setObjectName("page")
        page.setMinimumWidth(820)
        scroll_area.setWidget(page)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)

        page_header = QHBoxLayout()

        back_button = QPushButton(
            "← Back to roster"
        )
        back_button.setObjectName(
            "secondaryButton"
        )
        back_button.clicked.connect(
            self.show_home_page
        )

        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        self.player_page_title = QLabel(
            "Player details"
        )
        self.player_page_title.setObjectName(
            "pageTitle"
        )

        self.player_page_subtitle = QLabel(
            "Select a player from master_player_data.csv to view their boss gains."
        )
        self.player_page_subtitle.setObjectName(
            "pageSubtitle"
        )

        title_box.addWidget(
            self.player_page_title
        )
        title_box.addWidget(
            self.player_page_subtitle
        )

        page_header.addWidget(back_button)
        page_header.addSpacing(8)
        page_header.addLayout(title_box)
        page_header.addStretch(1)

        layout.addLayout(page_header)

        selector_panel = QFrame()
        selector_panel.setObjectName("panel")

        selector_layout = QHBoxLayout(
            selector_panel
        )
        selector_layout.setContentsMargins(
            16,
            13,
            16,
            13,
        )
        selector_layout.setSpacing(10)

        folder_label = QLabel(
            "Master data file"
        )
        folder_label.setObjectName("fieldLabel")

        self.folder_path_edit = QLineEdit()
        self.folder_path_edit.setReadOnly(True)
        self.folder_path_edit.setPlaceholderText(
            "master_player_data.csv not selected"
        )

        player_label = QLabel("Player")
        player_label.setObjectName("fieldLabel")

        self.player_combo = QComboBox()
        self.player_combo.setMinimumWidth(220)
        self.player_combo.currentIndexChanged.connect(
            self.load_selected_player_from_combo
        )

        selector_layout.addWidget(folder_label)
        selector_layout.addWidget(
            self.folder_path_edit,
            1,
        )
        selector_layout.addWidget(player_label)
        selector_layout.addWidget(
            self.player_combo
        )

        layout.addWidget(selector_panel)

        cards = QHBoxLayout()
        cards.setSpacing(12)

        self.player_card = SummaryCard("PLAYER")
        self.calculated_ehb_card = SummaryCard(
            "CALCULATED EHB"
        )
        self.matched_activities_card = SummaryCard(
            "KPH MATCHES"
        )

        cards.addWidget(self.player_card)
        cards.addWidget(
            self.calculated_ehb_card
        )
        cards.addWidget(
            self.matched_activities_card
        )

        layout.addLayout(cards)
        layout.addWidget(
            self.build_registration_panel()
        )

        table_header = QHBoxLayout()

        table_title = QLabel("Boss gains")
        table_title.setObjectName("sectionTitle")

        self.temple_source_label = QLabel(
            f"{TEMPLE_KPH_FILENAME}: not found"
        )
        self.temple_source_label.setObjectName(
            "mutedLabel"
        )

        self.stats_search_edit = QLineEdit()
        self.stats_search_edit.setPlaceholderText(
            "Filter bosses…"
        )
        self.stats_search_edit.setClearButtonEnabled(
            True
        )
        self.stats_search_edit.setMaximumWidth(280)
        self.stats_search_edit.textChanged.connect(
            self.filter_stats_table
        )

        table_header.addWidget(table_title)
        table_header.addSpacing(10)
        table_header.addWidget(
            self.temple_source_label
        )
        table_header.addStretch(1)
        table_header.addWidget(
            self.stats_search_edit
        )

        layout.addLayout(table_header)

        self.stats_table = QTableWidget(0, 4)
        self.stats_table.setHorizontalHeaderLabels(
            [
                "Boss / activity",
                "Gain",
                "Kills / hour",
                "Calculated EHB",
            ]
        )
        self.configure_table(self.stats_table)

        stats_header = (
            self.stats_table.horizontalHeader()
        )
        stats_header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        stats_header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        stats_header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        stats_header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.ResizeToContents,
        )

        charts_panel = QFrame()
        charts_panel.setObjectName("panel")
        charts_layout = QHBoxLayout(charts_panel)
        charts_layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )
        charts_layout.setSpacing(8)

        self.ehb_bar_chart = HorizontalEhbChart(
            "Calculated EHB by activity"
        )
        self.ehb_donut_chart = DonutEhbChart(
            "Calculated EHB distribution"
        )

        charts_layout.addWidget(
            self.ehb_bar_chart,
            3,
        )
        charts_layout.addWidget(
            self.ehb_donut_chart,
            2,
        )

        self.stats_table.setMinimumHeight(320)
        charts_panel.setMinimumHeight(280)

        content_splitter = QSplitter(
            Qt.Orientation.Vertical
        )
        content_splitter.setObjectName("playerContentSplitter")
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setOpaqueResize(True)
        content_splitter.setHandleWidth(12)
        content_splitter.setMinimumHeight(640)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 2)
        content_splitter.addWidget(self.stats_table)
        content_splitter.addWidget(charts_panel)
        content_splitter.setSizes([360, 280])

        layout.addWidget(content_splitter)
        layout.addStretch(1)

        return scroll_area

    def build_registration_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(
            18,
            15,
            18,
            17,
        )
        outer.setSpacing(12)

        title = QLabel("Player information")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.registration_player_value = (
            DetailValueLabel()
        )
        self.registration_alt_value = (
            DetailValueLabel()
        )
        self.registration_timezone_value = (
            DetailValueLabel()
        )
        self.registration_playtime_value = (
            DetailValueLabel()
        )
        self.registration_note_value = (
            DetailValueLabel()
        )

        self.add_detail_pair(
            grid,
            0,
            "Player name",
            self.registration_player_value,
            "Alt account",
            self.registration_alt_value,
        )
        self.add_detail_pair(
            grid,
            1,
            "Time zone",
            self.registration_timezone_value,
            "Play time",
            self.registration_playtime_value,
        )

        note_title = QLabel(
            "Note / preference"
        )
        note_title.setObjectName("detailTitle")

        grid.addWidget(
            note_title,
            2,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        grid.addWidget(
            self.registration_note_value,
            2,
            1,
            1,
            3,
        )

        outer.addLayout(grid)
        return panel

    @staticmethod
    def add_detail_pair(
        grid: QGridLayout,
        row: int,
        left_title: str,
        left_value: QLabel,
        right_title: str,
        right_value: QLabel,
    ) -> None:
        left_label = QLabel(left_title)
        left_label.setObjectName("detailTitle")

        right_label = QLabel(right_title)
        right_label.setObjectName("detailTitle")

        grid.addWidget(
            left_label,
            row,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        grid.addWidget(left_value, row, 1)

        grid.addWidget(
            right_label,
            row,
            2,
            Qt.AlignmentFlag.AlignTop,
        )
        grid.addWidget(right_value, row, 3)

    @staticmethod
    def configure_table(
        table: QTableWidget,
    ) -> None:
        table.setAlternatingRowColors(True)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setHighlightSections(
            False
        )
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        table.setShowGrid(False)
        table.setWordWrap(True)

    def apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#appRoot,
            QWidget#page,
            QStackedWidget,
            QScrollArea#playerScrollArea,
            QScrollArea#playerScrollArea > QWidget > QWidget {
                background: #0F1217;
                color: #E6E9EE;
                font-family: "Segoe UI", "Inter", sans-serif;
                font-size: 13px;
            }

            QFrame#topBar {
                background: #15191F;
                border-bottom: 1px solid #282E37;
            }

            QLabel#brandLabel {
                color: #F0F2F5;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 1px;
            }

            QLabel#pageTitle {
                color: #F3F4F6;
                font-size: 25px;
                font-weight: 750;
            }

            QLabel#pageSubtitle,
            QLabel#mutedLabel {
                color: #8D96A3;
            }

            QLabel#sectionTitle {
                color: #ECEFF3;
                font-size: 15px;
                font-weight: 700;
            }

            QLabel#fieldLabel,
            QLabel#detailTitle {
                color: #8F98A5;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#detailTitle {
                min-width: 92px;
            }

            QLabel#detailValue {
                color: #E0E4EA;
                padding: 1px 0;
            }

            QFrame#summaryCard,
            QFrame#panel {
                background: #171C23;
                border: 1px solid #2A313B;
                border-radius: 10px;
            }

            QLabel#cardTitle {
                color: #9099A6;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }

            QLabel#cardValue {
                color: #F1F2F4;
                font-size: 22px;
                font-weight: 750;
            }

            QLineEdit,
            QComboBox {
                background: #12161C;
                color: #E4E7EB;
                border: 1px solid #303843;
                border-radius: 7px;
                padding: 8px 10px;
                min-height: 22px;
                selection-background-color: #6E5931;
                selection-color: #FFFFFF;
            }

            QLineEdit:focus,
            QComboBox:focus {
                border: 1px solid #B88C42;
            }

            QLineEdit:read-only {
                color: #A7AFBA;
            }

            QComboBox QAbstractItemView {
                background: #171C23;
                color: #E4E7EB;
                border: 1px solid #303843;
                selection-background-color: #4C402A;
                selection-color: #FFFFFF;
            }

            QPushButton {
                background: #9A7438;
                color: #FFFFFF;
                border: none;
                border-radius: 7px;
                padding: 9px 14px;
                font-weight: 700;
            }

            QPushButton:hover {
                background: #AE8442;
            }

            QPushButton:pressed {
                background: #805F2D;
            }

            QPushButton:disabled {
                background: #292E35;
                color: #717985;
            }

            QPushButton#secondaryButton,
            QPushButton#navButton {
                background: #1A2028;
                color: #D7DBE1;
                border: 1px solid #303843;
            }

            QPushButton#secondaryButton:hover,
            QPushButton#navButton:hover {
                background: #222A34;
                border-color: #46515F;
            }

            QTableWidget {
                background: #14191F;
                alternate-background-color: #181E26;
                color: #E1E5EA;
                border: 1px solid #29313B;
                border-radius: 10px;
                selection-background-color: #403724;
                selection-color: #FFFFFF;
                padding: 2px;
            }

            QTableWidget::item {
                padding: 9px 8px;
                border-bottom: 1px solid #222A33;
            }

            QTableWidget::item:selected {
                background: #403724;
                color: #FFFFFF;
            }

            QHeaderView::section {
                background: #1B2129;
                color: #A9B0BA;
                border: none;
                border-bottom: 1px solid #303741;
                padding: 10px 8px;
                font-size: 11px;
                font-weight: 800;
            }

            QScrollArea#playerScrollArea {
                border: none;
            }

            QSplitter#playerContentSplitter::handle:vertical {
                background: #2E3742;
                border-top: 1px solid #414C59;
                border-bottom: 1px solid #181D23;
                margin: 3px 0;
            }

            QSplitter#playerContentSplitter::handle:vertical:hover {
                background: #9A7438;
            }

            QStatusBar {
                background: #15191F;
                color: #8D96A3;
                border-top: 1px solid #282E37;
            }

            QScrollBar:vertical {
                background: #101419;
                width: 12px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background: #3A424D;
                min-height: 28px;
                border-radius: 5px;
            }

            QScrollBar::handle:vertical:hover {
                background: #4A5563;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_home_page(self) -> None:
        self.pages.setCurrentIndex(
            HOME_PAGE_INDEX
        )

    def show_player_page(self) -> None:
        self.pages.setCurrentIndex(
            PLAYER_PAGE_INDEX
        )

    # ------------------------------------------------------------------
    # File locations and loading
    # ------------------------------------------------------------------

    def restore_master_data_file(self) -> None:
        stored_file = self.settings.value(
            "last_master_data_file",
            "",
            type=str,
        )

        if stored_file:
            stored_path = Path(stored_file)

            if stored_path.is_file():
                self.set_master_data_file(stored_path)
                return

        for base in (
            Path.cwd(),
            Path(__file__).resolve().parent,
        ):
            candidate = base / DEFAULT_MASTER_PLAYER_DATA_PATH

            if candidate.is_file():
                self.set_master_data_file(candidate)
                return

        self.load_master_player_data()
        self.refresh_home_page()

    def select_master_data_file(self) -> None:
        if self.master_data_path is not None:
            start_directory = str(self.master_data_path.parent)
        else:
            start_directory = str(Path.cwd())

        selected, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select master_player_data.csv",
            start_directory,
            "CSV files (*.csv);;All files (*)",
        )

        if selected:
            self.set_master_data_file(Path(selected))

    def set_master_data_file(
        self,
        selected_file: Path,
    ) -> None:
        selected_file = selected_file.expanduser().resolve()

        # Also accept the project root or the June Bingo data folder.
        if selected_file.is_dir():
            nested_candidate = (
                selected_file / DEFAULT_MASTER_PLAYER_DATA_PATH
            )
            direct_candidate = (
                selected_file / MASTER_PLAYER_DATA_FILENAME
            )

            if nested_candidate.is_file():
                selected_file = nested_candidate.resolve()
            elif direct_candidate.is_file():
                selected_file = direct_candidate.resolve()

        if not selected_file.is_file():
            QMessageBox.warning(
                self,
                "Master data file not found",
                (
                    "The selected master data file does not exist:\n"
                    f"{selected_file}"
                ),
            )
            return

        self.master_data_path = selected_file

        self.settings.setValue(
            "last_master_data_file",
            str(selected_file),
        )

        self.folder_path_edit.setText(str(selected_file))
        self.folder_path_edit.setToolTip(str(selected_file))

        self.refresh_all_data()

    def possible_project_roots(self) -> list[Path]:
        roots = [
            Path(__file__).resolve().parent,
            Path.cwd(),
        ]

        if self.master_data_path is not None:
            roots.append(self.master_data_path.parent)
            roots.extend(self.master_data_path.parents)

        unique_roots: list[Path] = []
        seen: set[Path] = set()

        for root in roots:
            root = root.resolve()

            if root not in seen:
                seen.add(root)
                unique_roots.append(root)

        return unique_roots

    def find_root_file(
        self,
        filename: str,
    ) -> Path | None:
        for root in self.possible_project_roots():
            candidate = root / filename

            if candidate.is_file():
                return candidate

        return None

    def load_project_data(self) -> None:
        self.load_bingo_registrations()
        self.load_temple_kph()

    def refresh_all_data(self) -> None:
        # Temple rates must load before master stats are converted to EHB.
        self.load_project_data()
        self.load_master_player_data()
        self.refresh_home_page()

        if (
            self.pages.currentIndex() == PLAYER_PAGE_INDEX
            and self.player_combo.count() > 0
        ):
            self.load_selected_player_from_combo()

    def load_bingo_registrations(self) -> None:
        self.bingo_data_path = self.find_root_file(
            BINGO_DATA_FILENAME
        )
        self.registrations = []

        if self.bingo_data_path is None:
            if hasattr(
                self,
                "home_source_label",
            ):
                self.home_source_label.setText(
                    f"{BINGO_DATA_FILENAME}: not found"
                )
            return

        try:
            self.registrations = (
                self.read_bingo_data_csv(
                    self.bingo_data_path
                )
            )
        except (
            OSError,
            csv.Error,
            ValueError,
        ) as error:
            QMessageBox.warning(
                self,
                "Could not read bingo data",
                (
                    f"Could not read:\n"
                    f"{self.bingo_data_path}\n\n"
                    f"{error}"
                ),
            )
            return

        if hasattr(
            self,
            "home_source_label",
        ):
            self.home_source_label.setText(
                f"{self.bingo_data_path.name} · "
                f"{len(self.registrations)} player(s)"
            )
            self.home_source_label.setToolTip(
                str(self.bingo_data_path)
            )

    @staticmethod
    def read_bingo_data_csv(
        csv_path: Path,
    ) -> list[Registration]:
        """
        Headerless source layout:

            0 date                  ignored
            1 player_name
            2 alt_account
            3 temp_delete_this      ignored
            4 time_zone
            5 note
            6 play_time
            7+ buy_in/export data   ignored
        """
        registrations: list[Registration] = []

        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.reader(handle)

            for row_number, raw_row in enumerate(
                reader,
                start=1,
            ):
                row = [
                    value.strip()
                    for value in raw_row
                ]

                if not row or not any(row):
                    continue

                if (
                    row_number == 1
                    and len(row) >= 2
                    and row[0].casefold() == "date"
                    and row[1].casefold()
                    == "player_name"
                ):
                    continue

                if len(row) < 7:
                    continue

                registrations.append(
                    Registration(
                        player_name=row[1],
                        alt_account=row[2],
                        time_zone=row[4],
                        note=row[5],
                        play_time=row[6],
                    )
                )

        return registrations

    def load_temple_kph(self) -> None:
        self.temple_kph_path = self.find_root_file(
            TEMPLE_KPH_FILENAME
        )
        self.temple_kph = {}

        if self.temple_kph_path is None:
            if hasattr(
                self,
                "temple_source_label",
            ):
                self.temple_source_label.setText(
                    f"{TEMPLE_KPH_FILENAME}: not found"
                )
            return

        try:
            self.temple_kph = (
                self.read_temple_kph_csv(
                    self.temple_kph_path
                )
            )
        except (
            OSError,
            csv.Error,
            ValueError,
        ) as error:
            QMessageBox.warning(
                self,
                "Could not read Temple KPH data",
                (
                    f"Could not read:\n"
                    f"{self.temple_kph_path}\n\n"
                    f"{error}"
                ),
            )
            return

        if hasattr(
            self,
            "temple_source_label",
        ):
            self.temple_source_label.setText(
                f"{self.temple_kph_path.name} · "
                f"{len(self.temple_kph)} activities"
            )
            self.temple_source_label.setToolTip(
                str(self.temple_kph_path)
            )

    @staticmethod
    def read_temple_kph_csv(
        csv_path: Path,
    ) -> dict[str, float]:
        rates: dict[str, float] = {}

        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.reader(handle)

            for row in reader:
                if len(row) < 2:
                    continue

                activity_name = row[0].strip()
                rate_text = row[1].strip()

                if not activity_name or not rate_text:
                    continue

                try:
                    rate = float(
                        rate_text.replace(",", "")
                    )
                except ValueError:
                    continue

                if (
                    not math.isfinite(rate)
                    or rate <= 0
                ):
                    continue

                rates[
                    normalize_activity_name(
                        activity_name
                    )
                ] = rate

        return rates

    def load_master_player_data(self) -> None:
        self.player_stats = {}
        self.player_display_names = {}
        self.calculated_ehb_by_player = {}
        self.master_skipped_rows = 0

        if self.master_data_path is None:
            for base in (
                Path.cwd(),
                Path(__file__).resolve().parent,
            ):
                candidate = base / DEFAULT_MASTER_PLAYER_DATA_PATH

                if candidate.is_file():
                    self.master_data_path = candidate.resolve()
                    self.folder_path_edit.setText(
                        str(self.master_data_path)
                    )
                    self.folder_path_edit.setToolTip(
                        str(self.master_data_path)
                    )
                    break

        if self.master_data_path is None:
            self.refresh_player_combo()
            return

        try:
            (
                self.player_stats,
                self.player_display_names,
                self.master_skipped_rows,
            ) = self.read_master_player_data_csv(
                self.master_data_path
            )
        except (
            OSError,
            csv.Error,
            ValueError,
        ) as error:
            QMessageBox.warning(
                self,
                "Could not read master player data",
                (
                    f"Could not read:\n"
                    f"{self.master_data_path}\n\n"
                    f"{error}"
                ),
            )
            self.refresh_player_combo()
            return

        for player_key, entries in self.player_stats.items():
            matched_values = [
                entry.calculated_ehb
                for entry in entries
                if entry.calculated_ehb is not None
            ]

            self.calculated_ehb_by_player[player_key] = (
                sum(matched_values)
                if matched_values
                else None
            )

        self.refresh_player_combo()

    def read_master_player_data_csv(
        self,
        csv_path: Path,
    ) -> tuple[
        dict[str, list[StatEntry]],
        dict[str, str],
        int,
    ]:
        """
        Read the combined player data file.

        Required headers:
            player, stat, gain

        Player names are grouped case-insensitively, with underscores treated
        as spaces. Ehb and Collections rows are deliberately ignored.
        """
        grouped_stats: dict[str, list[StatEntry]] = {}
        display_names: dict[str, str] = {}
        skipped_rows = 0

        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)

            if reader.fieldnames is None:
                raise ValueError(
                    "master_player_data.csv has no header row."
                )

            normalized_headers = {
                header.strip().casefold(): header
                for header in reader.fieldnames
                if header is not None
            }

            player_header = normalized_headers.get("player")
            stat_header = normalized_headers.get("stat")
            gain_header = normalized_headers.get("gain")

            if (
                player_header is None
                or stat_header is None
                or gain_header is None
            ):
                raise ValueError(
                    'master_player_data.csv must contain '
                    '"player", "stat", and "gain" columns.'
                )

            for row in reader:
                raw_player_name = (
                    row.get(player_header) or ""
                ).strip()
                stat_name = (
                    row.get(stat_header) or ""
                ).strip()
                gain_text = (
                    row.get(gain_header) or ""
                ).strip()

                if (
                    not raw_player_name
                    or not stat_name
                    or not gain_text
                ):
                    skipped_rows += 1
                    continue

                player_key = normalize_account_name(
                    raw_player_name
                )
                normalized_stat_name = normalize_activity_name(
                    stat_name
                )

                if not player_key:
                    skipped_rows += 1
                    continue

                if normalized_stat_name in {
                    "ehb",
                    "collections",
                }:
                    continue

                try:
                    gain = float(
                        gain_text.replace(",", "")
                    )
                except ValueError:
                    skipped_rows += 1
                    continue

                if not math.isfinite(gain):
                    skipped_rows += 1
                    continue

                kills_per_hour = self.temple_kph.get(
                    normalized_stat_name
                )

                calculated_ehb = (
                    gain / kills_per_hour
                    if kills_per_hour is not None
                    and kills_per_hour > 0
                    else None
                )

                display_names.setdefault(
                    player_key,
                    raw_player_name,
                )
                grouped_stats.setdefault(
                    player_key,
                    [],
                ).append(
                    StatEntry(
                        name=stat_name,
                        gain=gain,
                        kills_per_hour=kills_per_hour,
                        calculated_ehb=calculated_ehb,
                    )
                )

        for entries in grouped_stats.values():
            entries.sort(
                key=lambda entry: entry.gain,
                reverse=True,
            )

        return grouped_stats, display_names, skipped_rows

    def refresh_player_combo(self) -> None:
        previous_key = self.player_combo.currentData()

        self.player_combo.blockSignals(True)
        self.player_combo.clear()

        sorted_players = sorted(
            self.player_display_names.items(),
            key=lambda item: item[1].casefold(),
        )

        for player_key, display_name in sorted_players:
            self.player_combo.addItem(
                display_name,
                player_key,
            )

        previous_index = self.player_combo.findData(
            previous_key
        )

        if previous_index >= 0:
            self.player_combo.setCurrentIndex(
                previous_index
            )
        elif self.player_combo.count() > 0:
            self.player_combo.setCurrentIndex(0)

        self.player_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Home page
    # ------------------------------------------------------------------

    def refresh_home_page(self) -> None:
        self.home_table.setSortingEnabled(False)
        self.home_table.setRowCount(
            len(self.registrations)
        )

        for row_number, registration in enumerate(
            self.registrations
        ):
            common_index = row_number

            player_item = SortableItem(
                registration.player_name or "—",
                normalize_account_name(
                    registration.player_name
                ),
                common_index,
            )
            player_item.setForeground(
                QBrush(LINK_COLOR)
            )

            player_font = player_item.font()
            player_font.setBold(True)
            player_item.setFont(player_font)

            alt_item = SortableItem(
                registration.alt_account or "—",
                normalize_account_name(
                    registration.alt_account
                ),
                common_index,
            )

            timezone_item = SortableItem(
                registration.time_zone or "—",
                registration.time_zone.casefold(),
                common_index,
            )

            note_item = SortableItem(
                registration.note or "—",
                registration.note.casefold(),
                common_index,
            )
            note_item.setToolTip(
                registration.note
            )

            play_time_item = SortableItem(
                registration.play_time or "—",
                play_time_sort_key(
                    registration.play_time
                ),
                common_index,
            )
            play_time_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            player_key = (
                self.find_player_key_for_registration(
                    registration
                )
            )

            calculated_ehb = (
                self.calculated_ehb_by_player.get(
                    player_key
                )
                if player_key is not None
                else None
            )

            if calculated_ehb is None:
                ehb_item = SortableItem(
                    "—",
                    math.inf,
                    common_index,
                )
            else:
                ehb_item = NumericItem(
                    format_number(
                        calculated_ehb,
                        2,
                    ),
                    calculated_ehb,
                )
                ehb_item.setData(
                    Qt.ItemDataRole.UserRole,
                    common_index,
                )

            items = (
                player_item,
                alt_item,
                timezone_item,
                note_item,
                play_time_item,
                ehb_item,
            )

            for column, item in enumerate(items):
                self.home_table.setItem(
                    row_number,
                    column,
                    item,
                )

            self.home_table.setRowHeight(
                row_number,
                46,
            )

        self.home_table.setSortingEnabled(True)
        self.home_table.sortItems(
            0,
            Qt.SortOrder.AscendingOrder,
        )

        self.filter_home_table(
            self.home_search_edit.text()
        )

        matched_player_count = sum(
            value is not None
            for value
            in self.calculated_ehb_by_player.values()
        )

        if self.bingo_data_path is None:
            self.statusBar().showMessage(
                f"{BINGO_DATA_FILENAME} was not found."
            )
        else:
            self.statusBar().showMessage(
                f"Loaded {len(self.registrations)} players; "
                f"calculated EHB for {matched_player_count} "
                "player(s) in the master file."
            )

    def filter_home_table(
        self,
        text: str,
    ) -> None:
        search_text = text.strip().casefold()

        for row in range(
            self.home_table.rowCount()
        ):
            row_text = " ".join(
                self.home_table.item(
                    row,
                    column,
                ).text().casefold()
                for column in range(
                    self.home_table.columnCount()
                )
                if self.home_table.item(
                    row,
                    column,
                )
                is not None
            )

            self.home_table.setRowHidden(
                row,
                bool(search_text)
                and search_text not in row_text,
            )

    def registration_index_for_home_row(
        self,
        row: int,
    ) -> int | None:
        item = self.home_table.item(row, 0)

        if item is None:
            return None

        value = item.data(
            Qt.ItemDataRole.UserRole
        )

        return value if isinstance(value, int) else None

    def home_table_cell_clicked(
        self,
        row: int,
        column: int,
    ) -> None:
        if column == 0:
            self.open_home_row(row)

    def home_table_cell_double_clicked(
        self,
        row: int,
        _column: int,
    ) -> None:
        self.open_home_row(row)

    def open_selected_home_player(self) -> None:
        selected_rows = (
            self.home_table.selectionModel()
            .selectedRows()
        )

        if not selected_rows:
            QMessageBox.information(
                self,
                "Select a player",
                "Select a roster row first.",
            )
            return

        self.open_home_row(
            selected_rows[0].row()
        )

    def open_home_row(self, row: int) -> None:
        registration_index = (
            self.registration_index_for_home_row(
                row
            )
        )

        if registration_index is None:
            return

        if not (
            0
            <= registration_index
            < len(self.registrations)
        ):
            return

        registration = self.registrations[
            registration_index
        ]

        self.open_registration(registration)

    # ------------------------------------------------------------------
    # Player page
    # ------------------------------------------------------------------

    def open_registration(
        self,
        registration: Registration,
    ) -> None:
        player_key = self.find_player_key_for_registration(
            registration
        )

        if player_key is not None:
            combo_index = self.player_combo.findData(
                player_key
            )

            if combo_index >= 0:
                self.player_combo.blockSignals(True)
                self.player_combo.setCurrentIndex(
                    combo_index
                )
                self.player_combo.blockSignals(False)

            self.load_player_details(
                player_key,
                preferred_registration=registration,
            )
        else:
            self.clear_stats()
            self.display_registration(registration)

            display_name = (
                registration.player_name
                or registration.alt_account
                or "Unknown player"
            )

            self.player_card.set_value(display_name)
            self.player_page_title.setText(display_name)
            self.player_page_subtitle.setText(
                "Registration found, but no matching player "
                "was found in master_player_data.csv."
            )

            self.statusBar().showMessage(
                f"No master data found for {display_name}."
            )

        self.pages.setCurrentIndex(
            PLAYER_PAGE_INDEX
        )

    def find_player_key_for_registration(
        self,
        registration: Registration,
    ) -> str | None:
        wanted_names = {
            normalize_account_name(
                registration.player_name
            ),
            normalize_account_name(
                registration.alt_account
            ),
        }
        wanted_names.discard("")

        for player_key in self.player_stats:
            if player_key in wanted_names:
                return player_key

        return None

    def load_selected_player_from_combo(
        self,
        _index: int = -1,
    ) -> None:
        player_key = self.player_combo.currentData()

        if not isinstance(player_key, str) or not player_key:
            self.clear_stats()
            self.clear_registration()
            return

        self.load_player_details(player_key)

    def load_player_details(
        self,
        player_key: str,
        preferred_registration: Registration
        | None = None,
    ) -> None:
        entries = self.player_stats.get(
            player_key,
            [],
        )
        player_name = self.player_display_names.get(
            player_key,
            player_key,
        )

        self.current_entries = entries
        self.populate_stats_table(entries)

        matched_entries = [
            entry
            for entry in entries
            if entry.calculated_ehb is not None
        ]

        calculated_ehb_total = sum(
            entry.calculated_ehb
            for entry in matched_entries
            if entry.calculated_ehb is not None
        )

        self.player_card.set_value(player_name)
        self.calculated_ehb_card.set_value(
            format_number(
                calculated_ehb_total,
                2,
            )
            if matched_entries
            else "—"
        )
        self.matched_activities_card.set_value(
            f"{len(matched_entries)} / {len(entries)}"
        )

        chart_data = [
            (
                entry.name,
                entry.calculated_ehb,
            )
            for entry in matched_entries
            if entry.calculated_ehb is not None
        ]

        self.ehb_bar_chart.set_data(chart_data)
        self.ehb_donut_chart.set_data(chart_data)

        matches = self.find_registrations_for_name(
            player_name
        )

        registration = (
            preferred_registration
            if preferred_registration is not None
            else matches[0]
            if matches
            else None
        )

        if registration is not None:
            self.display_registration(registration)
        else:
            self.clear_registration()

        self.player_page_title.setText(player_name)
        self.player_page_subtitle.setText(
            f"Stats from {MASTER_PLAYER_DATA_FILENAME}"
        )

        self.filter_stats_table(
            self.stats_search_edit.text()
        )

        message = (
            f"Loaded {len(entries)} boss gains for "
            f"{player_name}; calculated EHB from "
            f"{len(matched_entries)} Temple KPH match(es)."
        )

        if self.master_skipped_rows:
            message += (
                f" The master file contains "
                f"{self.master_skipped_rows} skipped invalid row(s)."
            )

        self.statusBar().showMessage(message)

    def find_registrations_for_name(
        self,
        player_name: str,
    ) -> list[Registration]:
        wanted = normalize_account_name(
            player_name
        )

        return [
            registration
            for registration in self.registrations
            if wanted
            in {
                normalize_account_name(
                    registration.player_name
                ),
                normalize_account_name(
                    registration.alt_account
                ),
            }
        ]

    def display_registration(
        self,
        registration: Registration,
    ) -> None:
        self.registration_player_value.set_value(
            registration.player_name
        )
        self.registration_alt_value.set_value(
            registration.alt_account
        )
        self.registration_timezone_value.set_value(
            registration.time_zone
        )
        self.registration_playtime_value.set_value(
            registration.play_time
        )
        self.registration_note_value.set_value(
            registration.note
        )

    def clear_registration(self) -> None:
        for label in (
            self.registration_player_value,
            self.registration_alt_value,
            self.registration_timezone_value,
            self.registration_playtime_value,
            self.registration_note_value,
        ):
            label.set_value("")

    def populate_stats_table(
        self,
        entries: list[StatEntry],
    ) -> None:
        self.stats_table.setSortingEnabled(False)
        self.stats_table.setRowCount(
            len(entries)
        )

        for row_number, entry in enumerate(
            entries
        ):
            stat_item = QTableWidgetItem(
                entry.name
            )
            stat_item.setToolTip(entry.name)

            gain_item = NumericItem(
                format_number(entry.gain),
                entry.gain,
            )

            if entry.kills_per_hour is None:
                kph_item = SortableItem(
                    "—",
                    math.inf,
                )
            else:
                kph_item = NumericItem(
                    format_number(
                        entry.kills_per_hour,
                        2,
                    ),
                    entry.kills_per_hour,
                )

            if entry.calculated_ehb is None:
                ehb_item = SortableItem(
                    "—",
                    math.inf,
                )
            else:
                ehb_item = NumericItem(
                    format_number(
                        entry.calculated_ehb,
                        2,
                    ),
                    entry.calculated_ehb,
                )

            self.stats_table.setItem(
                row_number,
                0,
                stat_item,
            )
            self.stats_table.setItem(
                row_number,
                1,
                gain_item,
            )
            self.stats_table.setItem(
                row_number,
                2,
                kph_item,
            )
            self.stats_table.setItem(
                row_number,
                3,
                ehb_item,
            )

            self.stats_table.setRowHeight(
                row_number,
                40,
            )

        self.stats_table.setSortingEnabled(True)
        self.stats_table.sortItems(
            1,
            Qt.SortOrder.DescendingOrder,
        )

    def filter_stats_table(
        self,
        text: str,
    ) -> None:
        search_text = text.strip().casefold()

        for row in range(
            self.stats_table.rowCount()
        ):
            item = self.stats_table.item(
                row,
                0,
            )

            boss_name = (
                item.text().casefold()
                if item is not None
                else ""
            )

            self.stats_table.setRowHidden(
                row,
                bool(search_text)
                and search_text not in boss_name,
            )

    def clear_stats(self) -> None:
        self.current_entries = []
        self.stats_table.setRowCount(0)
        self.calculated_ehb_card.set_value("—")
        self.matched_activities_card.set_value("0 / 0")
        self.ehb_bar_chart.set_data([])
        self.ehb_donut_chart.set_data([])


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName(
        APP_ORGANIZATION
    )
    app.setApplicationName(APP_NAME)

    window = BingoDashboard()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
