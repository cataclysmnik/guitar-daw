"""
Mixer Widget — Nothing-style flat design.
Two-column strip body:
  Col 1 (left): full-height level meter
  Col 2 (right): volume fader on top, pan knob below
Visible track borders, M/S at bottom.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSlider,
    QPushButton, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from widgets.knob import CustomKnob
from widgets.level_meter import LevelMeter

# ─────────────────────────────────────────────────────────────────────────────
# Design tokens
# ─────────────────────────────────────────────────────────────────────────────
BG           = "#000000"
CARD_BG      = "#0b0b0b"
CARD_BORDER  = "#363638"      # clearly visible
GAP_COLOR    = "#000000"      # gap between strips (= outer bg)
CARD_SEL     = "#ffffff"
TEXT_DIM     = "#555558"
TEXT_BRIGHT  = "#e0e0e0"
ACCENT       = "#ff0033"
MUTE_ON      = "#ff9900"
SOLO_ON      = "#ffffff"
FADER_TRACK  = "#1e1e1e"
FADER_FILL   = "#c8c8c8"
FADER_THUMB  = "#d0d0d0"
MASTER_BDR   = "#3a3a3e"
SEP_COLOR    = "#222224"

STRIP_W      = 120   # px — wide enough for 65px min knob + meter + margins


# ─────────────────────────────────────────────────────────────────────────────
# Pan knob with L/C/R labels
# ─────────────────────────────────────────────────────────────────────────────
class _PanKnob(CustomKnob):
    def __init__(self, default_val=0.0, parent=None):
        super().__init__(
            label="PAN",
            min_val=-1.0,
            max_val=1.0,
            default_val=default_val,
            unit="",
            decimals=2,
            parent=parent,
        )

    def get_value_str(self) -> str:
        v = self.value
        if abs(v) < 0.01:
            return "C"
        elif v < 0:
            return f"L{abs(v)*100:.0f}"
        else:
            return f"R{v*100:.0f}"


# ─────────────────────────────────────────────────────────────────────────────
# Shared QSS for ChannelStrip
# ─────────────────────────────────────────────────────────────────────────────
_CARD_QSS = f"""
    QWidget#ChannelStrip {{
        background-color: {CARD_BG};
        border: 1px solid {CARD_BORDER};
    }}
    QWidget#ChannelStrip[selected="true"] {{
        border: 1px solid {CARD_SEL};
        background-color: #101012;
    }}
    QLabel#ChName {{
        color: {TEXT_BRIGHT};
        font-family: "Consolas","Courier New",monospace;
        font-size: 9px;
        font-weight: bold;
        letter-spacing: 1px;
        background: transparent;
    }}
    QLabel#ChDb {{
        color: {TEXT_DIM};
        font-family: "Consolas","Courier New",monospace;
        font-size: 8px;
        background: transparent;
    }}
    /* Fader */
    QSlider#ChFader::groove:vertical {{
        background: {FADER_TRACK};
        width: 2px;
        border-radius: 1px;
    }}
    QSlider#ChFader::add-page:vertical {{
        background: {FADER_FILL};
        width: 2px;
    }}
    QSlider#ChFader::sub-page:vertical {{
        background: {FADER_TRACK};
        width: 2px;
    }}
    QSlider#ChFader::handle:vertical {{
        background: {FADER_THUMB};
        width: 28px;
        height: 4px;
        margin-left: -13px;
        margin-right: -13px;
        border-radius: 0px;
    }}
    QSlider#ChFader::handle:vertical:hover {{
        background: {ACCENT};
    }}
    /* M/S buttons */
    QPushButton#BtnMute {{
        background: transparent;
        border: 1px solid #666668;
        color: #cccccc;
        font-family: "Consolas","Courier New",monospace;
        font-size: 9px;
        font-weight: bold;
        border-radius: 0px;
    }}
    QPushButton#BtnMute:hover  {{ border-color: {MUTE_ON}; color: {MUTE_ON}; }}
    QPushButton#BtnMute:checked {{ background: {MUTE_ON}; border-color: {MUTE_ON}; color:#000; }}
    QPushButton#BtnSolo {{
        background: transparent;
        border: 1px solid #666668;
        color: #cccccc;
        font-family: "Consolas","Courier New",monospace;
        font-size: 9px;
        font-weight: bold;
        border-radius: 0px;
    }}
    QPushButton#BtnSolo:hover  {{ border-color: {SOLO_ON}; color: {SOLO_ON}; }}
    QPushButton#BtnSolo:checked {{ background: {SOLO_ON}; border-color: {SOLO_ON}; color:#000; }}
"""


# ─────────────────────────────────────────────────────────────────────────────
# ChannelStrip
# ─────────────────────────────────────────────────────────────────────────────
class ChannelStrip(QWidget):
    def __init__(self, track, audio_engine, parent=None):
        super().__init__(parent)
        self.track = track
        self.audio_engine = audio_engine
        self._guard = False

        self.setObjectName("ChannelStrip")
        self.setProperty("selected", "false")
        self.setFixedWidth(STRIP_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(_CARD_QSS)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(7, 7, 7, 7)
        root.setSpacing(5)

        # ── Header: track name + M/S buttons ────────────────────────
        header = QHBoxLayout()
        header.setSpacing(4)
        header.setContentsMargins(0, 0, 0, 0)

        self.lbl_name = QLabel(self.track.name)
        self.lbl_name.setObjectName("ChName")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.lbl_name, 1)

        self.btn_mute = QPushButton("M")
        self.btn_mute.setObjectName("BtnMute")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setChecked(self.track.mute)
        self.btn_mute.setFixedSize(22, 18)
        self.btn_mute.clicked.connect(self._on_mute)
        header.addWidget(self.btn_mute)

        self.btn_solo = QPushButton("S")
        self.btn_solo.setObjectName("BtnSolo")
        self.btn_solo.setCheckable(True)
        self.btn_solo.setChecked(self.track.solo)
        self.btn_solo.setFixedSize(22, 18)
        self.btn_solo.clicked.connect(self._on_solo)
        header.addWidget(self.btn_solo)

        root.addLayout(header)
        root.addWidget(self._hsep())

        # ── 2-column body ────────────────────────────────────────────
        # Col 1: level meter (full height)
        # Col 2: fader on top, dB label, then pan knob below
        body = QHBoxLayout()
        body.setSpacing(6)
        body.setContentsMargins(0, 0, 0, 0)

        # --- Column 1: Level meter ---
        self.meter = LevelMeter()
        self.meter.setFixedWidth(14)
        self.meter.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        body.addWidget(self.meter)

        # Thin vertical divider between columns
        body.addWidget(self._vsep())

        # --- Column 2: fader + dB + pan knob ---
        col2 = QVBoxLayout()
        col2.setSpacing(4)
        col2.setContentsMargins(0, 0, 0, 0)

        # Fader
        self.fader = QSlider(Qt.Orientation.Vertical)
        self.fader.setObjectName("ChFader")
        self.fader.setMinimum(-600)
        self.fader.setMaximum(60)
        self.fader.setValue(int(self.track.volume * 10))
        self.fader.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.fader.valueChanged.connect(self._on_fader)
        col2.addWidget(self.fader, 1)

        # dB readout
        self.lbl_db = QLabel()
        self.lbl_db.setObjectName("ChDb")
        self.lbl_db.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._refresh_db(self.track.volume)
        col2.addWidget(self.lbl_db)

        col2.addWidget(self._hsep())

        # Pan knob — give it its natural/minimum size, no clipping
        self.pan_knob = _PanKnob(default_val=self.track.pan)
        self.pan_knob.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.pan_knob.valueChanged.connect(self._on_pan)
        col2.addWidget(self.pan_knob, 0, Qt.AlignmentFlag.AlignHCenter)

        body.addLayout(col2, 1)
        root.addLayout(body, 1)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _hsep():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"color:{SEP_COLOR}; background:{SEP_COLOR}; max-height:1px;")
        return f

    @staticmethod
    def _vsep():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet(f"color:{SEP_COLOR}; background:{SEP_COLOR}; max-width:1px;")
        return f

    def mark_dirty(self):
        main_win = self.window()
        if main_win and hasattr(main_win, 'mark_project_dirty'):
            main_win.mark_project_dirty()

    def _on_fader(self, v):
        if self._guard:
            return
        db = v / 10.0
        self.track.volume = db
        self._refresh_db(db)
        self.mark_dirty()

    def _on_pan(self, v):
        self.track.pan = v
        self.mark_dirty()

    def _on_mute(self):
        self.track.mute = self.btn_mute.isChecked()
        self.mark_dirty()

    def _on_solo(self):
        self.track.solo = self.btn_solo.isChecked()
        self.mark_dirty()

    def _refresh_db(self, db):
        self.lbl_db.setText("-∞ dB" if db <= -60.0 else f"{db:+.1f} dB")

    # ── Public API ────────────────────────────────────────────────────────

    def tick(self):
        self.meter.set_level(self.track.level_history)
        self.lbl_name.setText(self.track.name)

    def set_selected(self, sel: bool):
        self.setProperty("selected", "true" if sel else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.set_selected(True)
        super().mousePressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Master strip
# ─────────────────────────────────────────────────────────────────────────────
class MasterStrip(QWidget):
    STRIP_W = 90

    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        self.setObjectName("MasterStrip")
        self.setFixedWidth(self.STRIP_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._build()
        self._apply_style()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(7, 7, 7, 7)
        root.setSpacing(5)

        lbl = QLabel("MASTER")
        lbl.setObjectName("MasterName")
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root.addWidget(lbl)

        root.addWidget(self._hsep())

        body = QHBoxLayout()
        body.setSpacing(6)
        body.setContentsMargins(0, 0, 0, 0)

        # L/R meters
        self.meter_l = LevelMeter()
        self.meter_l.setFixedWidth(12)
        self.meter_l.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        body.addWidget(self.meter_l)

        self.meter_r = LevelMeter()
        self.meter_r.setFixedWidth(12)
        self.meter_r.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        body.addWidget(self.meter_r)

        body.addWidget(self._vsep())

        # Fader + dB
        col = QVBoxLayout()
        col.setSpacing(4)
        col.setContentsMargins(0, 0, 0, 0)

        self.fader = QSlider(Qt.Orientation.Vertical)
        self.fader.setObjectName("MasterFader")
        self.fader.setMinimum(-600)
        self.fader.setMaximum(60)
        self.fader.setValue(int(self.audio_engine.main_volume * 10))
        self.fader.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.fader.valueChanged.connect(self._on_fader)
        col.addWidget(self.fader, 1)

        self.lbl_db = QLabel()
        self.lbl_db.setObjectName("MasterDb")
        self._refresh_db(self.audio_engine.main_volume)
        col.addWidget(self.lbl_db)

        body.addLayout(col, 1)
        root.addLayout(body, 1)

    @staticmethod
    def _hsep():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"color:{SEP_COLOR}; background:{SEP_COLOR}; max-height:1px;")
        return f

    @staticmethod
    def _vsep():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet(f"color:{SEP_COLOR}; background:{SEP_COLOR}; max-width:1px;")
        return f

    def _on_fader(self, v):
        db = v / 10.0
        self.audio_engine.main_volume = db
        self._refresh_db(db)

    def _refresh_db(self, db):
        self.lbl_db.setText("-∞ dB" if db <= -60.0 else f"{db:+.1f} dB")

    def update_volume_ui(self):
        self.fader.setValue(int(self.audio_engine.main_volume * 10))
        self._refresh_db(self.audio_engine.main_volume)

    def tick(self, level):
        self.meter_l.set_level(level[0])
        self.meter_r.set_level(level[1])

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget#MasterStrip {{
                background-color: {CARD_BG};
                border: 1px solid {MASTER_BDR};
            }}
            QLabel#MasterName {{
                color: {TEXT_BRIGHT};
                font-family: "Consolas","Courier New",monospace;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 2px;
                background: transparent;
            }}
            QLabel#MasterDb {{
                color: {TEXT_DIM};
                font-family: "Consolas","Courier New",monospace;
                font-size: 8px;
                background: transparent;
            }}
            QSlider#MasterFader::groove:vertical {{
                background: {FADER_TRACK};
                width: 2px;
                border-radius: 1px;
            }}
            QSlider#MasterFader::add-page:vertical {{
                background: {FADER_FILL};
                width: 2px;
            }}
            QSlider#MasterFader::sub-page:vertical {{
                background: {FADER_TRACK};
                width: 2px;
            }}
            QSlider#MasterFader::handle:vertical {{
                background: {FADER_THUMB};
                width: 28px;
                height: 4px;
                margin-left: -13px;
                margin-right: -13px;
                border-radius: 0px;
            }}
            QSlider#MasterFader::handle:vertical:hover {{
                background: {ACCENT};
            }}
        """)


# ─────────────────────────────────────────────────────────────────────────────
# MixerWidget
# ─────────────────────────────────────────────────────────────────────────────
class MixerWidget(QWidget):
    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        self.strips: list[ChannelStrip] = []
        self.setObjectName("MixerWidget")
        self._build()
        self._apply_style()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setObjectName("MixerScroll")
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._container.setObjectName("MixerContainer")
        self._strips_layout = QHBoxLayout(self._container)
        self._strips_layout.setContentsMargins(8, 8, 8, 8)
        # Use spacing=6 so there is a visible black gap between card borders
        self._strips_layout.setSpacing(6)
        self._strips_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, 1)

        div = QFrame()
        div.setObjectName("MixerDiv")
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFixedWidth(1)
        outer.addWidget(div)

        self.master = MasterStrip(self.audio_engine)
        outer.addWidget(self.master)

    def rebuild(self):
        for s in self.strips:
            self._strips_layout.removeWidget(s)
            s.deleteLater()
        self.strips.clear()
        for track in self.audio_engine.tracks:
            s = ChannelStrip(track, self.audio_engine)
            self._strips_layout.addWidget(s)
            self.strips.append(s)

    def _tick(self):
        for s in self.strips:
            s.tick()
        self.master.tick(self.audio_engine.main_level_history)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget#MixerWidget   {{ background-color: {BG}; }}
            QScrollArea#MixerScroll {{ background-color: {BG}; border: none; }}
            QWidget#MixerContainer  {{ background-color: {BG}; }}
            QFrame#MixerDiv         {{ background-color: #2a2a2a; border: none; }}
        """)
