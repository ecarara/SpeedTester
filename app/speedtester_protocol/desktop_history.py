# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Native local dashboard. Receipts, filters and charts; no browser or login."""

from datetime import datetime
from decimal import Decimal
import tkinter as tk
from tkinter import ttk
from .models import METRICS
from .central_slots import central_zone
from .desktop_text import problem_text

BACKGROUND, PAPER, INK, MUTED, ACCENT = (
    "#f2f1e9",
    "#ffffff",
    "#112b2a",
    "#49615c",
    "#c1ef55",
)


class HistoryScreen:
    def open_history(self):
        if self.busy:
            return
        self.history_cursor = None
        self.history_stack = []
        self.show("history")
        self.load_history()

    def history_time(self, stamp):
        if stamp is None:
            return self.t("not_recorded")
        zone = (self.history_data or {}).get("integration", {}).get("timezone", "UTC")
        try:
            return datetime.fromtimestamp(stamp, central_zone(zone)).strftime(
                "%Y-%m-%d %H:%M"
            )
        except (ValueError, OverflowError, OSError):
            return self.t("not_recorded")

    @staticmethod
    def history_value(row):
        if row["value"] is None:
            return "—"
        scale, unit = {
            "bit/s": (1_000_000, "Mbps"),
            "us": (1000, "ms"),
            "ppm": (10000, "%"),
            "ms": (1000, "s"),
            "byte": (1_000_000, "MB"),
            "count": (1, ""),
        }[row["unit"]]
        value = format(Decimal(row["value"]) / scale, ".3f").rstrip("0").rstrip(".")
        return value + (" " + unit if unit else "")

    def history_query(self):
        return {
            "metric": self.history_metric,
            "days": self.history_days,
            "delivery": self.history_delivery,
            "before": self.history_cursor,
        }

    def load_history(self):
        if self.busy:
            return
        query = self.history_query()

        def read():
            try:
                result = self.controller.call("history", query)
                if not result.get("ok"):
                    return {
                        "ok": True,
                        "history_error": "history_upgrade"
                        if result.get("code") == "unknown_local_operation"
                        else "history_failed",
                    }
                return result
            except (OSError, ValueError):
                return {"ok": True, "history_error": "history_failed"}

        def received(result):
            if query != self.history_query():
                self.after(0, self.load_history)
                return
            self.history_data = result
            if self.page == "history":
                self.render()

        self.work(read, received, busy_key="history_loading")

    def history_filter(self, field, value):
        setattr(self, field, value)
        self.history_cursor = None
        self.history_stack = []
        self.load_history()

    def history_page(self, older):
        if self.busy:
            return
        if older:
            cursor = (self.history_data or {}).get("next_cursor")
            if cursor is None:
                return
            self.history_stack.append(self.history_cursor)
            self.history_cursor = cursor
        elif self.history_stack:
            self.history_cursor = self.history_stack.pop()
        self.load_history()

    def page_history(self):
        self.heading("history_title", "history_detail")
        tabs = ttk.Notebook(self.content)
        tabs.pack(fill="both", expand=True)
        results = tk.Frame(tabs, bg=BACKGROUND, padx=10, pady=8)
        integration_container = tk.Frame(tabs, bg=BACKGROUND)
        canvas = tk.Canvas(integration_container, bg=BACKGROUND, highlightthickness=0)
        scroll = ttk.Scrollbar(
            integration_container, orient="vertical", command=canvas.yview
        )
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        integration = tk.Frame(canvas, bg=BACKGROUND, padx=16, pady=14)
        item = canvas.create_window(0, 0, window=integration, anchor="nw")
        integration.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>", lambda event: canvas.itemconfigure(item, width=event.width)
        )
        tabs.add(results, text=self.t("history_results"))
        tabs.add(integration_container, text=self.t("history_integration"))
        self.history_tabs = tabs
        tabs.select(self.history_tab)

        def remember_tab(_event):
            self.history_tab = tabs.index(tabs.select())

        tabs.bind("<<NotebookTabChanged>>", remember_tab)
        footer = tk.Frame(results, bg=BACKGROUND)
        footer.pack(side="bottom", fill="x", pady=(6, 0))
        self.button(footer, "history_refresh", self.load_history).pack(side="left")
        older = self.button(footer, "history_older", lambda: self.history_page(True))
        older.pack(side="right")
        newer = self.button(footer, "history_newer", lambda: self.history_page(False))
        newer.pack(side="right", padx=6)
        older.configure(
            state="normal"
            if (self.history_data or {}).get("next_cursor")
            else "disabled"
        )
        newer.configure(state="normal" if self.history_stack else "disabled")
        filters = tk.Frame(results, bg=BACKGROUND)
        filters.pack(fill="x")
        definitions = (
            (
                "history_metric",
                [(m, "history_metric_" + m) for m in METRICS],
                self.history_metric,
            ),
            (
                "history_period",
                [
                    (1, "history_day"),
                    (7, "history_week"),
                    (30, "history_month"),
                    (0, "history_anytime"),
                ],
                self.history_days,
            ),
            (
                "history_delivery",
                [
                    ("all", "history_all"),
                    ("accepted", "history_accepted"),
                    ("pending", "history_pending"),
                    ("quarantined", "history_quarantined"),
                ],
                self.history_delivery,
            ),
        )
        self.history_filters = {}
        for column, (label, options, selected) in enumerate(definitions):
            filters.columnconfigure(column, weight=1)
            box = tk.Frame(filters, bg=BACKGROUND)
            box.grid(row=0, column=column, sticky="ew", padx=(0, 8))
            self.label(box, self.t(label), size=9, color=MUTED).pack(anchor="w")
            variable = tk.StringVar(
                value=next(self.t(key) for value, key in options if value == selected)
            )
            control = ttk.Combobox(
                box,
                textvariable=variable,
                values=[self.t(key) for _, key in options],
                state="readonly",
                width=16,
            )
            control.pack(fill="x")
            attribute = ("history_metric", "history_days", "history_delivery")[column]
            control.bind(
                "<<ComboboxSelected>>",
                lambda _event, c=control, opts=options, attr=attribute: (
                    self.history_filter(attr, opts[c.current()][0])
                ),
            )
            self.history_filters[attribute] = control
        data = self.history_data or {}
        if data.get("history_error"):
            self.label(results, self.t(data["history_error"]), size=12, width=570).pack(
                fill="x", pady=20
            )
            self.label(
                integration, self.t(data["history_error"]), size=12, width=550
            ).pack(fill="x")
            return
        counts = data.get("counts", {})
        summary = tk.Frame(results, bg=BACKGROUND)
        summary.pack(fill="x", pady=(8, 6))
        for column, key in enumerate(("accepted", "pending", "quarantined")):
            summary.columnconfigure(column, weight=1)
            card = tk.Frame(summary, bg=INK, padx=12, pady=6)
            card.grid(row=0, column=column, sticky="ew", padx=(0, 5))
            self.label(
                card, str(counts.get(key, 0)), bold=True, size=18, color=ACCENT
            ).pack(anchor="w")
            self.label(
                card, self.t("history_" + key), size=9, color=PAPER, width=170
            ).pack(anchor="w")
        self.label(results, self.t("history_counts"), size=8, color=MUTED).pack(
            anchor="w"
        )
        chart = tk.Canvas(results, bg=INK, height=105, highlightthickness=0)
        chart.pack(fill="x", pady=(5, 4))
        chart.bind("<Configure>", lambda _event: self.draw_history_chart(chart))
        self.history_chart = chart
        table_frame = tk.Frame(results, bg=BACKGROUND)
        table_frame.pack(fill="both", expand=True)
        columns = ("at", "value", "quality", "delivery", "closure")
        tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=4, selectmode="browse"
        )
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        tree.configure(yscrollcommand=scrollbar.set)
        for column, key, width in zip(
            columns,
            (
                "history_date",
                "history_value",
                "history_quality",
                "history_delivery",
                "history_closure",
            ),
            (135, 100, 90, 135, 100),
        ):
            tree.heading(column, text=self.t(key))
            tree.column(column, width=width, minwidth=60, stretch=True)
        quality = {
            "valid": "history_valid",
            "error": "history_error",
            "not-supported": "history_unavailable",
            "not-collected": "history_not_collected",
        }
        for index, row in enumerate(data.get("rows", [])):
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    self.history_time(row["at"]),
                    self.history_value(row),
                    self.t(quality[row["quality"]]),
                    self.t("history_" + row["delivery"]),
                    self.t(
                        "history_complete"
                        if row["attempt_complete"]
                        else "history_incomplete"
                    ),
                ),
            )
        self.history_tree = tree
        note = (
            self.t("history_corrupt").format(count=data["unreadable"])
            if data.get("unreadable")
            else self.t("history_empty")
            if not data.get("rows")
            else self.t("history_page").format(count=len(data["rows"]))
        )
        self.label(results, note, size=9, color=MUTED, width=600).pack(
            fill="x", pady=(4, 0)
        )
        self.label(
            results, self.t("history_chart_note"), size=9, color=MUTED, width=600
        ).pack(fill="x", pady=(3, 0))
        state = data.get("integration", {})
        self.label(
            integration,
            self.t("history_linked" if state.get("paired") else "history_unlinked"),
            bold=True,
            size=18,
        ).pack(fill="x", pady=(0, 12))
        for key, value in (
            ("history_server", state.get("origin") or "—"),
            (
                "history_schedule",
                self.t("enabled" if state.get("enabled") else "paused"),
            ),
            (
                "history_last_confirmation"
                if data.get("confirmation_scope") == "saved"
                else "history_page_confirmation",
                self.history_time(data.get("last_confirmed_at")),
            ),
            ("history_observed", self.history_time(state.get("observed_at"))),
        ):
            self.label(integration, self.t(key), size=9, color=MUTED).pack(
                anchor="w", pady=(5, 0)
            )
            self.label(integration, value, size=12, width=540).pack(
                fill="x", pady=(0, 6)
            )
        problem = self.status_problem(state.get("problem"))
        if problem:
            self.label(
                integration,
                problem_text(self.locale, problem, compact=True),
                size=10,
                width=540,
                color="#705016",
            ).pack(fill="x", pady=8)
        self.label(
            integration, self.t("history_scope"), size=10, width=540, color=MUTED
        ).pack(fill="x", pady=(10, 0))
        self.label(
            integration, self.t("history_hint"), size=10, width=540, color=MUTED
        ).pack(fill="x", pady=(8, 0))

    def draw_history_chart(self, canvas):
        canvas.delete("all")
        rows = sorted(
            (self.history_data or {}).get("rows", []), key=lambda row: row["at"]
        )
        valid = [row["value"] for row in rows if row["value"] is not None]
        width = max(200, canvas.winfo_width())
        height = max(80, canvas.winfo_height())
        canvas.create_text(
            12,
            12,
            text=self.t("history_chart"),
            anchor="nw",
            fill=PAPER,
            font=("Helvetica", 9, "bold"),
        )
        if not valid:
            canvas.create_text(
                width / 2, height / 2 + 10, text="—", fill=ACCENT, font=("Georgia", 25)
            )
            return
        top = max(max(valid), 1)
        left, right, bottom = 14, width - 14, height - 26
        for fraction in (0, 0.5, 1):
            y = 34 + fraction * (bottom - 34)
            canvas.create_line(left, y, right, y, fill="#294945", dash=(2, 5))
        begin = min(row["at"] for row in rows)
        end = max(row["at"] for row in rows)
        canvas.create_text(
            left,
            height - 5,
            text=self.history_time(begin),
            anchor="sw",
            fill="#c5d6cf",
            font=("Helvetica", 8),
        )
        if end != begin:
            canvas.create_text(
                right,
                height - 5,
                text=self.history_time(end),
                anchor="se",
                fill="#c5d6cf",
                font=("Helvetica", 8),
            )
        previous = None
        for index, row in enumerate(rows):
            if row["value"] is None:
                previous = None
                continue
            x = (
                left + (row["at"] - begin) / max(1, end - begin) * (right - left)
                if len(rows) > 1
                else (left + right) / 2
            )
            y = bottom - row["value"] / top * (bottom - 34)
            if previous:
                canvas.create_line(*previous, x, y, fill=ACCENT, width=2)
            color = (
                ACCENT
                if row["attempt_complete"]
                else "#edba72"
                if row["delivery"] == "pending"
                else "#c5d6cf"
            )
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=INK)
            previous = (x, y)
        best = max(
            (row for row in rows if row["value"] is not None),
            key=lambda row: row["value"],
        )
        canvas.create_text(
            width - 12,
            12,
            text=self.history_value(best),
            anchor="ne",
            fill=ACCENT,
            font=("Helvetica", 10, "bold"),
        )
