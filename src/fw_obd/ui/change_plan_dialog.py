"""Change Plan review dialog — shows a structured ChangePlan for approval.

v1 is dry-run: clicking "Apply" returns Accepted but the caller does NOT push
to a device. It exists to prove the plan format and approval UX before any real
SSH execution is wired in.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from fw_obd.ai.change_planner import ChangePlan, RiskLevel

_RISK_COLORS = {
    RiskLevel.LOW: "#27ae60",
    RiskLevel.MEDIUM: "#f39c12",
    RiskLevel.HIGH: "#e74c3c",
}


class ChangePlanDialog(QDialog):
    """Displays a ChangePlan with its commands; Apply is dry-run in v1."""

    def __init__(self, plan: ChangePlan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle("Review Change Plan")
        self.setMinimumSize(620, 520)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # -- Intent --
        intent = QLabel(self._plan.intent or "Proposed change")
        intent.setWordWrap(True)
        intent.setStyleSheet("font-size: 16px; font-weight: bold;")
        root.addWidget(intent)

        # -- Risk + backup badges --
        badges = QHBoxLayout()
        risk_color = _RISK_COLORS.get(self._plan.risk_level, "#95a5a6")
        risk = QLabel(f"Risk: {self._plan.risk_level.value.upper()}")
        risk.setStyleSheet(
            f"background-color: {risk_color}; color: white; padding: 4px 12px; "
            "border-radius: 10px; font-weight: bold; font-size: 12px;"
        )
        badges.addWidget(risk)

        if self._plan.backup_needed:
            backup = QLabel("Backup before apply")
            backup.setStyleSheet(
                "background-color: #2980b9; color: white; padding: 4px 12px; "
                "border-radius: 10px; font-weight: bold; font-size: 12px;"
            )
            badges.addWidget(backup)
        badges.addStretch()
        root.addLayout(badges)

        # -- Rationale --
        if self._plan.rationale:
            rationale = QLabel(self._plan.rationale)
            rationale.setWordWrap(True)
            rationale.setStyleSheet("color: #555; font-size: 13px;")
            root.addWidget(rationale)

        # -- Warnings --
        for warning in self._plan.warnings:
            w = QLabel(f"⚠️  {warning}")
            w.setWordWrap(True)
            w.setStyleSheet(
                "background-color: #fdf2e9; color: #b9770e; padding: 8px 12px; "
                "border-radius: 6px; font-size: 12px;"
            )
            root.addWidget(w)

        # -- Commands --
        cmds_label = QLabel(f"Commands ({len(self._plan.commands)})")
        cmds_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        root.addWidget(cmds_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        clayout = QVBoxLayout(container)
        clayout.setSpacing(8)
        clayout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for idx, cmd in enumerate(self._plan.commands, start=1):
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background-color: #ffffff; border: 1px solid #dde3e9; "
                "border-radius: 6px; }"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            desc = QLabel(f"{idx}. {cmd.description}")
            desc.setWordWrap(True)
            desc.setStyleSheet("font-weight: bold; font-size: 12px; border: none;")
            cli = QLabel(cmd.cli)
            cli.setWordWrap(True)
            cli.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cli.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 12px; color: #1e2a38; "
                "background-color: #f4f6f8; padding: 6px; border-radius: 4px; border: none;"
            )
            cl.addWidget(desc)
            cl.addWidget(cli)
            clayout.addWidget(card)

        scroll.setWidget(container)
        root.addWidget(scroll, stretch=1)

        # -- Dry-run notice --
        notice = QLabel("DRY RUN — Apply previews the plan only. Nothing is pushed to the device.")
        notice.setStyleSheet("color: #7f8c8d; font-style: italic; font-size: 12px;")
        root.addWidget(notice)

        # -- Buttons --
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet("padding: 10px 16px; border-radius: 6px;")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        apply_btn = QPushButton("Apply (dry run)")
        apply_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; padding: 10px 20px; "
            "border: none; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2471a3; }"
        )
        apply_btn.clicked.connect(self.accept)
        buttons.addWidget(apply_btn)
        root.addLayout(buttons)
