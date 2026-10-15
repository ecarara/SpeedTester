# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Native graphical installer. All I/O runs off the Tk event loop."""
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
from .desktop_controller import DEFAULT_SERVER
from .desktop_service import DesktopConfiguration
from .desktop_text import TEXT, LANGUAGES

BACKGROUND, PAPER, INK, MUTED, ACCENT = "#f2f1e9", "#ffffff", "#112b2a", "#49615c", "#c1ef55"


class Installer(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.locale, self.page, self.operation = "pt-BR", "welcome", "install"
        self.snapshot, self.pairing = {}, None
        self.events = queue.Queue()
        self.busy = False
        self.geometry("1040x820")
        self.minsize(960, 780)
        self.configure(bg=BACKGROUND)
        self.fields = {key: tk.StringVar(value=value) for key, value in {
            "origin": DEFAULT_SERVER, "operator": "", "country": "BR", "region": "", "city": "",
            "host": "", "port": "5201", "hours": "1"}.items()}
        self.access, self.link = tk.StringVar(), tk.StringVar()
        self.contribute, self.purge = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        self.languages = tk.StringVar(value="Português")
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("TEntry", padding=8, fieldbackground=PAPER, foreground=INK)
        self.style.configure("TCombobox", padding=7, fieldbackground=PAPER, foreground=INK)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.render()
        self.after(100, self.drain)

    def t(self, key):
        return TEXT[self.locale][key]

    def label(self, parent, text, *, size=12, color=INK, bold=False, width=None, background=None):
        return tk.Label(parent, text=text, fg=color, bg=background or parent.cget("bg"),
            font=("Helvetica", size, "bold" if bold else "normal"), justify="left", anchor="w",
            wraplength=width or 660)

    def button(self, parent, key, command, primary=False):
        return tk.Button(parent, text=self.t(key), command=command, bg=ACCENT if primary else PAPER,
            fg=INK, activebackground="#b1df47", activeforeground=INK, relief="flat", borderwidth=0,
            padx=18, pady=12, font=("Helvetica", 12, "bold"), cursor="hand2", takefocus=True)

    def render(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.title(self.t("title"))
        rail = tk.Frame(self, bg=INK, width=245)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self.label(rail, "CARARALAB", color=ACCENT, bold=True, size=13).pack(anchor="w", padx=25, pady=(36, 0))
        tk.Label(rail, text="SPEED\nTESTER", fg=PAPER, bg=INK, font=("Georgia", 30, "bold"),
            justify="left", anchor="w").pack(anchor="w", padx=24, pady=(18, 24))
        self.label(rail, self.t("tagline"), color="#c5d6cf", size=15, width=200).pack(anchor="w", padx=25)
        tk.Frame(rail, bg="#36504a", height=1).pack(fill="x", padx=25, pady=32)
        self.label(rail, self.t("navigation"), color="#94b6a7", size=9, width=200).pack(anchor="w", padx=25)
        for number, key in (("01", "install"), ("02", "repair"), ("03", "uninstall")):
            self.label(rail, number + "   " + self.t(key), color=PAPER, size=11, width=205).pack(anchor="w", padx=25, pady=(18, 0))
        self.label(rail, self.t("footer"), color="#94b6a7", size=10, width=200).pack(side="bottom", anchor="w", padx=25, pady=25)
        shell = tk.Frame(self, bg=BACKGROUND)
        shell.pack(side="left", fill="both", expand=True, padx=30, pady=24)
        header = tk.Frame(shell, bg=BACKGROUND)
        header.pack(fill="x")
        self.label(header, self.t("language"), size=10, color=MUTED).pack(side="right", padx=10)
        choice = ttk.Combobox(header, values=list(LANGUAGES), textvariable=self.languages, state="readonly", width=13)
        choice.pack(side="right")
        choice.bind("<<ComboboxSelected>>", self.change_language)
        banner = "preview" if self.controller.preview else "experimental"
        self.label(shell, self.t(banner), size=10, color="#705016", width=680).pack(anchor="w", pady=(18, 0))
        self.content = tk.Frame(shell, bg=BACKGROUND)
        self.content.pack(fill="both", expand=True, pady=(24, 0))
        getattr(self, "page_" + self.page)()
        self.feedback = self.label(shell, self.t("busy") if self.busy else "", color=MUTED, size=10)
        self.feedback.pack(fill="x", pady=(12, 0))

    def change_language(self, _event=None):
        self.locale = LANGUAGES[self.languages.get()]
        self.access.set("")
        self.link.set("")
        self.render()

    def heading(self, title, detail):
        tk.Label(self.content, text=self.t(title), bg=BACKGROUND, fg=INK, font=("Georgia", 25),
            anchor="w", justify="left", wraplength=670).pack(fill="x", pady=(0, 14))
        self.label(self.content, self.t(detail), color=MUTED, width=670).pack(fill="x", pady=(0, 22))

    def show(self, page):
        self.page = page
        self.render()

    def page_welcome(self):
        self.heading("welcome", "intro")
        for operation, detail in (("install", "install_detail"), ("repair", "repair_detail"), ("uninstall", "uninstall_detail")):
            card = tk.Frame(self.content, bg=PAPER, padx=18, pady=14)
            card.pack(fill="x", pady=(0, 12))
            self.button(card, operation, lambda action=operation: self.choose(action), primary=operation == "install").pack(anchor="w")
            self.label(card, self.t(detail), color=MUTED, size=11, width=610).pack(anchor="w", pady=(8, 0))
        self.button(self.content, "status", self.load_status).pack(anchor="w", pady=10)

    def choose(self, operation):
        if self.busy:
            return
        self.operation = operation
        if operation == "repair":
            if messagebox.askyesno(self.t("repair"), self.t("repair_confirm"), parent=self):
                self.work(lambda: self.controller.native("repair"), lambda _result: self.load_status())
        else:
            self.show("remove" if operation == "uninstall" else "configure")

    def page_configure(self):
        self.heading("configure", "configure_detail")
        tk.Checkbutton(self.content, text=self.t("contribute"), variable=self.contribute, bg=BACKGROUND,
            fg=INK, activebackground=BACKGROUND, font=("Helvetica", 12, "bold"), anchor="w").pack(fill="x", pady=(0, 16))
        grid = tk.Frame(self.content, bg=BACKGROUND)
        grid.pack(fill="x")
        for column in (0, 1):
            grid.columnconfigure(column, weight=1)
        for index, key in enumerate(("origin", "operator", "country", "region", "city", "host", "port", "hours")):
            cell = tk.Frame(grid, bg=BACKGROUND)
            cell.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 14), pady=(0, 10))
            self.label(cell, self.t(key), size=10, color=MUTED).pack(anchor="w", pady=(0, 4))
            ttk.Entry(cell, textvariable=self.fields[key], width=25).pack(fill="x")
        for column, (key, variable, choices) in enumerate((("access", self.access, ("fiber", "coaxial", "radio", "satellite", "cellular", "dsl", "other", "unknown")),
                ("link", self.link, ("ethernet", "wifi")))):
            cell = tk.Frame(grid, bg=BACKGROUND)
            cell.grid(row=4, column=column, sticky="ew", padx=(0, 14), pady=(0, 10))
            self.label(cell, self.t(key), size=10, color=MUTED).pack(anchor="w", pady=(0, 4))
            ttk.Combobox(cell, values=[self.t(choice) for choice in choices], textvariable=variable, state="readonly", width=25).pack(fill="x")
        self.label(self.content, self.t("target_notice"), color=MUTED, size=10).pack(fill="x", pady=(6, 10))
        self.button(self.content, "data", lambda: self.open_url(self.fields["origin"].get(), "/data")).pack(anchor="w")
        actions = tk.Frame(self.content, bg=BACKGROUND)
        actions.pack(fill="x", pady=(18, 0))
        self.button(actions, "back", lambda: self.show("welcome")).pack(side="left")
        self.button(actions, "save" if self.operation == "configure" else "continue", self.install, primary=True).pack(side="right")

    def configuration(self):
        if not self.contribute.get():
            return None
        access_keys = ("fiber", "coaxial", "radio", "satellite", "cellular", "dsl", "other", "unknown")
        access = next((key for key in access_keys if self.t(key) == self.access.get()), None)
        link = next((key for key in ("ethernet", "wifi") if self.t(key) == self.link.get()), None)
        value = lambda key: " ".join(self.fields[key].get().split())
        return DesktopConfiguration(origin=value("origin"), profile={"version": 1, "operator": value("operator"),
            "country_code": value("country").upper(), "region": value("region"), "city": value("city"),
            "access_type": access, "link_type": link}, host=value("host"), port=int(value("port")),
            interval_hours=int(value("hours")), contribute=True).model_dump()

    def install(self):
        try:
            configuration = self.configuration()
        except ValueError:
            messagebox.showerror(self.t("configure"), self.t("invalid"), parent=self)
            return
        action = self.operation
        def operation():
            if action == "install":
                self.controller.native("install")
            deadline = time.monotonic() + 45
            while True:
                try:
                    status = self.controller.call("status")
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.5)
            if configuration:
                status = self.controller.call("configure", configuration)
            elif action == "configure":
                # Explicit opt-out also pauses the schedule and all contribution.
                status = self.controller.call("disconnect")
            return status
        def completed(result):
            self.snapshot = result
            self.show("pair" if configuration else "status")
        self.work(operation, completed)

    def page_pair(self):
        self.heading("pair_title", "pair_detail")
        if self.pairing:
            tk.Label(self.content, text=self.pairing["user_code"], bg=INK, fg=ACCENT,
                padx=30, pady=18, font=("Courier", 30, "bold")).pack(fill="x", pady=(0, 16))
            self.label(self.content, self.t("fingerprint"), bold=True).pack(anchor="w")
            self.label(self.content, self.pairing["fingerprint"], size=11, width=650).pack(fill="x", pady=(6, 12))
            self.label(self.content, self.t("expires"), size=11, color=MUTED).pack(fill="x", pady=(0, 12))
            self.button(self.content, "open_pair", lambda: self.open_pair()).pack(anchor="w")
            self.label(self.content, self.t("waiting_pair"), color=MUTED).pack(fill="x", pady=16)
        self.label(self.content, self.t("data_detail"), size=11, color=MUTED).pack(fill="x", pady=(0, 18))
        self.button(self.content, "retry_pair" if self.pairing else "pair", self.begin_pairing, primary=True).pack(anchor="w")
        self.button(self.content, "later", self.finish_pairing).pack(anchor="w", pady=12)

    def begin_pairing(self):
        def completed(result):
            if result.get("paired"):
                self.snapshot = result
                self.show("status")
                return
            self.pairing = result.get("pairing")
            self.show("pair")
            self.after(5000, self.poll_pairing)
        self.work(lambda: self.controller.call("pair"), completed)

    def poll_pairing(self):
        if self.page != "pair" or self.busy:
            return
        def completed(result):
            self.snapshot = result
            if result.get("paired"):
                self.pairing = None
                self.show("status")
            else:
                self.pairing = result.get("pairing")
                self.render()
                self.after(5000, self.poll_pairing)
        self.work(lambda: self.controller.call("status"), completed)

    def finish_pairing(self):
        self.work(lambda: self.controller.call("cancel_pairing"), lambda result: self.received_status(result))

    def open_pair(self):
        if self.pairing and not self.controller.preview:
            webbrowser.open(self.pairing["verification_uri"] + "?locale=" + self.locale)

    def open_url(self, origin, path):
        from .client import HTTPS
        try:
            origin = HTTPS(origin).origin
        except ValueError:
            return
        if not self.controller.preview:
            webbrowser.open(origin + path + "?locale=" + self.locale)

    def received_status(self, result):
        self.snapshot = result
        self.show("status")

    def load_status(self):
        self.work(lambda: self.controller.call("status"), self.received_status)

    def page_status(self):
        self.heading("status", "status_detail")
        if self.snapshot:
            for key, value in (("running", "✓"), ("paired" if self.snapshot.get("paired") else "unpaired", "●"),
                    ("enabled" if self.snapshot.get("measurements_enabled") else "paused", "●"),
                    ("pending", str(self.snapshot.get("pending", 0))), ("quarantined", str(self.snapshot.get("quarantined", 0)))):
                row = tk.Frame(self.content, bg=PAPER, padx=18, pady=13)
                row.pack(fill="x", pady=(0, 8))
                self.label(row, self.t(key), size=12).pack(side="left")
                self.label(row, value, bold=True).pack(side="right")
        if self.snapshot.get("paired"):
            key = "pause" if self.snapshot.get("measurements_enabled") else "enable"
            self.button(self.content, key, lambda: self.schedule(key), primary=True).pack(anchor="w", pady=(16, 10))
        self.button(self.content, "manage", self.configure_existing).pack(anchor="w", pady=6)
        self.button(self.content, "account", lambda: self.open_url(self.fields["origin"].get(), "/account")).pack(anchor="w", pady=6)
        self.button(self.content, "home", lambda: self.show("welcome")).pack(anchor="w", pady=12)

    def configure_existing(self):
        if self.busy:
            return
        stored = self.snapshot.get("configuration")
        if stored:
            profile = stored["profile"]
            values = {**profile, "origin": stored["origin"], "country": profile["country_code"],
                "host": stored["host"], "port": str(stored["port"]), "hours": str(stored["interval_hours"])}
            for key, variable in self.fields.items():
                variable.set(values[key])
            self.access.set(self.t(profile["access_type"]))
            self.link.set(self.t(profile["link_type"]))
            self.contribute.set(stored["contribute"])
        self.operation = "configure"
        self.show("configure")

    def schedule(self, operation):
        if operation == "enable" and not messagebox.askyesno(self.t("enable"), self.t("enable_confirm"), parent=self):
            return
        self.work(lambda: self.controller.call(operation), self.received_status)

    def page_remove(self):
        self.heading("remove_title", "remove_detail")
        tk.Checkbutton(self.content, text=self.t("purge"), variable=self.purge, bg=BACKGROUND,
            fg=INK, activebackground=BACKGROUND, wraplength=650, justify="left",
            font=("Helvetica", 12), anchor="w").pack(fill="x", pady=(8, 24))
        self.label(self.content, self.t("revoke_notice"), color=MUTED).pack(fill="x", pady=(0, 20))
        self.button(self.content, "account", lambda: self.open_url(self.fields["origin"].get(), "/account")).pack(anchor="w", pady=(0, 24))
        self.button(self.content, "uninstall", self.uninstall, primary=True).pack(anchor="w", pady=10)
        self.button(self.content, "back", lambda: self.show("welcome")).pack(anchor="w", pady=10)

    def uninstall(self):
        if not messagebox.askyesno(self.t("uninstall"), self.t("remove_confirm"), parent=self):
            return
        purge = self.purge.get()
        def completed(result):
            message = self.t("purged" if purge else "preserved")
            if result.get("reboot_required"):
                message += "\n\n" + self.t("reboot")
            messagebox.showinfo(self.t("removed"), message, parent=self)
            self.show("welcome")
        self.work(lambda: self.controller.native("uninstall", purge), completed)

    def work(self, operation, completed):
        if self.busy:
            return
        self.busy = True
        self.feedback.configure(text=self.t("busy"))
        def worker():
            try:
                self.events.put((True, operation(), completed))
            except Exception:
                self.events.put((False, None, completed))
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        try:
            success, result, completed = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.feedback.configure(text="")
            if success and result.get("ok"):
                completed(result)
            else:
                code = result.get("code") if result else None
                key = "no_runner" if code == "iperf3_required" else "blocked" if code else "error"
                messagebox.showerror(self.t("title"), self.t(key), parent=self)
        self.after(100, self.drain)

    def close(self):
        if not self.busy:
            self.destroy()

    def smoke_test(self):
        # Real Tk widgets and all translations; the controller never touches I/O.
        for locale in TEXT:
            self.locale = locale
            for page in ("welcome", "configure", "pair", "status", "remove"):
                self.show(page)
                self.update()
                assert self.winfo_exists()
        self.destroy()
