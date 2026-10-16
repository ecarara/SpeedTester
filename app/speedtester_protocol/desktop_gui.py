# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Native graphical installer. All I/O runs off the Tk event loop."""
import queue
import threading
import time
import unicodedata
import tkinter as tk
from tkinter import messagebox, ttk
from .desktop_controller import DEFAULT_SERVER
from .desktop_service import DesktopConfiguration
from .desktop_text import TEXT, LANGUAGES
from .version import CLIENT_VERSION, build_label, diagnostic_text
from .input_methods import bind_dead_keys
from .schedule import local_timezone
from .disclosure import DISCLOSURE_CATALOG
from .desktop_links import portal_url, pairing_url, request_browser
from .profile_text import uppercase_text

BACKGROUND, PAPER, INK, MUTED, ACCENT = "#f2f1e9", "#ffffff", "#112b2a", "#49615c", "#c1ef55"


class Installer(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.locale, self.page, self.operation = "pt-BR", "welcome", "install"
        self.form_locale = self.locale
        self.snapshot, self.pairing = {}, None
        self.pairing_state, self.pair_poll = "idle", None
        self.events = queue.Queue()
        self.busy = False
        self.browser_events = queue.Queue()
        self.portal_requests = queue.Queue()
        self.account_pending = False
        self.geometry("1040x820")
        self.minsize(960, 780)
        self.configure(bg=BACKGROUND)
        self.schedule_timezone = local_timezone()
        self.fields = {key: tk.StringVar(value=value) for key, value in {
            "origin": DEFAULT_SERVER, "operator": "", "country": "BR", "region": "", "city": ""}.items()}
        # Preserve spaces/cursor while typing; collapse whitespace on validation.
        for field in ("operator", "country", "region", "city"):
            variable = self.fields[field]
            variable.trace_add("write", lambda *_args, value=variable: self.uppercase_field(value))
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

    @staticmethod
    def uppercase_field(variable):
        value = variable.get()
        converted = uppercase_text(value)
        if value != converted:
            variable.set(converted)

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

    def ask_confirmation(self, title_key, message_key):
        """Own translated buttons; native message boxes follow the OS locale."""
        existing = getattr(self, "confirmation_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return False
        window = tk.Toplevel(self)
        self.confirmation_window = window
        window.title(self.t(title_key))
        window.configure(bg=BACKGROUND, padx=24, pady=20)
        window.transient(self)
        window.resizable(False, False)
        answer = False
        def finish(value=False):
            nonlocal answer
            answer = value
            if window.winfo_exists():
                window.destroy()
        window.protocol("WM_DELETE_WINDOW", finish)
        self.label(window, self.t(message_key), size=13, width=460).pack(fill="x")
        actions = tk.Frame(window, bg=BACKGROUND)
        actions.pack(fill="x", pady=(24, 0))
        yes = self.button(actions, "yes", lambda: finish(True), primary=True)
        no = self.button(actions, "no", finish)
        yes.pack(side="left")
        no.pack(side="right")
        no.configure(default="active")
        window.bind("<Escape>", lambda _event: finish())
        def enter(_event):
            finish(window.focus_get() == yes)
            return "break"
        window.bind("<Return>", enter)
        window.update_idletasks()
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        x = max(0, self.winfo_rootx() + (self.winfo_width() - width) // 2)
        y = max(0, self.winfo_rooty() + (self.winfo_height() - height) // 2)
        window.geometry(f"+{x}+{y}")
        window.wait_visibility()
        window.grab_set()
        no.focus_set()
        self.wait_window(window)
        return answer

    def status_time(self, value):
        if not isinstance(value, (int, float)) or value <= 0:
            return self.t("not_recorded")
        from datetime import datetime
        from .central_slots import central_zone
        zone = (self.snapshot.get("configuration") or {}).get("timezone", self.schedule_timezone)
        try:
            return datetime.fromtimestamp(value, central_zone(zone)).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, KeyError, OverflowError, OSError):
            return self.t("not_recorded")

    def render(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.title(self.t("title")+" — "+CLIENT_VERSION)
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
        self.label(rail, self.t("footer")+"\n"+build_label(), color="#94b6a7", size=10, width=200).pack(side="bottom", anchor="w", padx=25, pady=25)
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
        # Translate selected labels instead of silently discarding form choices.
        previous = getattr(self, "form_locale", "pt-BR")
        for variable, choices in ((self.access, ("fiber", "coaxial", "radio", "satellite", "cellular", "dsl", "other", "unknown")),
                (self.link, ("ethernet", "wifi"))):
            selected = next((key for key in choices if TEXT[previous][key] == variable.get()), None)
            variable.set(self.t(selected) if selected else "")
        self.form_locale = self.locale
        self.render()

    def heading(self, title, detail):
        tk.Label(self.content, text=self.t(title), bg=BACKGROUND, fg=INK, font=("Georgia", 25),
            anchor="w", justify="left", wraplength=670).pack(fill="x", pady=(0, 14))
        description=self.t(detail)
        if self.page=="status":description+="\n"+self.t("version_label")+": "+build_label()
        self.label(self.content, description, color=MUTED, width=670).pack(fill="x", pady=(0, 22))

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
        if operation == "uninstall":
            # Destructive opt-in belongs to this confirmation, not a previous
            # cancelled or completed uninstall in the same window.
            self.purge.set(False)
        if operation == "repair":
            if self.ask_confirmation("repair", "repair_confirm"):
                self.work(lambda: self.controller.native("repair"), lambda _result: self.load_status())
        else:
            self.show("remove" if operation == "uninstall" else "configure")

    def page_configure(self):
        self.entries={}
        self.heading("configure", "configure_detail")
        tk.Checkbutton(self.content, text=self.t("contribute"), variable=self.contribute, bg=BACKGROUND,
            fg=INK, activebackground=BACKGROUND, font=("Helvetica", 12, "bold"), anchor="w").pack(fill="x", pady=(0, 16))
        grid = tk.Frame(self.content, bg=BACKGROUND)
        grid.pack(fill="x")
        for column in (0, 1):
            grid.columnconfigure(column, weight=1)
        for index, key in enumerate(("origin", "operator", "country", "region", "city")):
            cell = tk.Frame(grid, bg=BACKGROUND)
            cell.grid(row=index // 2, column=index % 2, columnspan=2 if key=="city" else 1, sticky="ew", padx=(0, 14), pady=(0, 10))
            self.label(cell, self.t(key), size=10, color=MUTED).pack(anchor="w", pady=(0, 4))
            entry=ttk.Entry(cell, textvariable=self.fields[key], width=25)
            entry.pack(fill="x")
            bind_dead_keys(entry)
            self.entries[key]=entry
        for column, (key, variable, choices) in enumerate((("access", self.access, ("fiber", "coaxial", "radio", "satellite", "cellular", "dsl", "other", "unknown")),
                ("link", self.link, ("ethernet", "wifi")))):
            cell = tk.Frame(grid, bg=BACKGROUND)
            cell.grid(row=3, column=column, sticky="ew", padx=(0, 14), pady=(0, 10))
            self.label(cell, self.t(key), size=10, color=MUTED).pack(anchor="w", pady=(0, 4))
            ttk.Combobox(cell, values=[self.t(choice) for choice in choices], textvariable=variable, state="readonly", width=25).pack(fill="x")
        self.label(self.content, self.t("schedule_notice").format(timezone=self.schedule_timezone)+"\n"+self.t("target_notice"), color=MUTED, size=10).pack(fill="x", pady=(6, 10))
        self.data_button = self.button(self.content, "data", self.show_disclosure)
        self.data_button.pack(anchor="w")
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
        value = lambda key: unicodedata.normalize("NFC", " ".join(self.fields[key].get().split()))
        return DesktopConfiguration(origin=value("origin"), profile={"version": 1, "operator": value("operator"),
            "country_code": value("country").upper(), "region": value("region"), "city": value("city"),
            "access_type": access, "link_type": link},
            timezone=self.schedule_timezone, contribute=True).model_dump()

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
            else:
                # Explicit opt-out also pauses the schedule and all contribution.
                status = self.controller.call("disconnect")
            return status
        def completed(result):
            self.snapshot = result
            if configuration and not result.get("paired"):
                self.show("pair")
                self.begin_pairing()
            else:
                self.received_status(result)
        self.work(operation, completed)

    def page_pair(self):
        self.heading("pair_title", "pair_detail")
        if self.pairing:
            self.label(self.content, self.t("pair_code"), bold=True).pack(anchor="w", pady=(0, 8))
            tk.Label(self.content, text=self.pairing["user_code"], bg=INK, fg=ACCENT,
                padx=22, pady=14, font=("Courier", 30, "bold")).pack(fill="x", pady=(0, 8))
            self.button(self.content, "copy_code", self.copy_pairing_code).pack(anchor="w", pady=(0, 12))
            self.label(self.content, self.t("fingerprint"), bold=True).pack(anchor="w")
            self.label(self.content, self.pairing["fingerprint"], size=10, width=650).pack(fill="x", pady=(4, 8))
            expires = time.strftime("%H:%M:%S", time.localtime(self.pairing["expires_at"]))
            self.label(self.content, self.t("code_deadline").format(time=expires), size=11, color=MUTED).pack(fill="x", pady=(0, 8))
            self.button(self.content, "open_pair", self.open_pair, primary=True).pack(anchor="w")
            self.label(self.content, self.t("waiting_pair"), color=MUTED).pack(fill="x", pady=10)
        else:
            state = {"generating": "generating_code", "expired": "code_expired", "failed": "code_failed"}
            self.label(self.content, self.t(state.get(self.pairing_state, "code_needed")), color=MUTED).pack(fill="x", pady=(0, 16))
        self.label(self.content, self.t("data_detail"), size=10, color=MUTED).pack(fill="x", pady=(0, 12))
        if self.pairing_state != "generating":
            self.button(self.content, "retry_pair" if self.pairing else "pair", self.begin_pairing).pack(anchor="w")
        self.button(self.content, "later", self.finish_pairing).pack(anchor="w", pady=8)

    def copy_pairing_code(self):
        if self.pairing and self.pairing["expires_at"] > time.time():
            self.clipboard_clear()
            self.clipboard_append(self.pairing["user_code"])
            self.feedback.configure(text=self.t("code_copied"))
        else:
            self.poll_pairing()

    def schedule_pair_poll(self):
        if self.pair_poll is not None:
            self.after_cancel(self.pair_poll)
        self.pair_poll = self.after(1000, self.poll_pairing)

    def received_pairing(self, result):
        previous, previous_state = self.pairing, self.pairing_state
        self.snapshot = result
        self.pairing = result.get("pairing")
        if result.get("paired"):
            self.show("status")
            return
        expired = self.pairing_state == "expired" or result.get("code") == "pairing_expired" or (previous and previous["expires_at"] <= time.time())
        self.pairing_state = "ready" if self.pairing else "expired" if expired else "failed"
        # Stable status polling must not destroy the copyable portal window,
        # keyboard focus or the button the participant is about to click.
        if self.page != "pair" or previous != self.pairing or previous_state != self.pairing_state:
            self.show("pair")
        if self.pairing:
            self.schedule_pair_poll()

    def begin_pairing(self):
        if self.busy:
            return
        self.pairing_state = "generating"
        self.show("pair")
        self.work(lambda: self.controller.call("pair"), self.received_pairing)

    def poll_pairing(self):
        if self.pair_poll is not None:
            self.after_cancel(self.pair_poll)
            self.pair_poll = None
        if self.page != "pair":
            return
        if self.busy:
            self.schedule_pair_poll()
            return
        self.work(lambda: self.controller.call("status"), self.received_pairing)

    def finish_pairing(self):
        def completed(result):
            self.pairing = None
            self.received_status(result)
        self.work(lambda: self.controller.call("cancel_pairing"), completed)

    def show_disclosure(self):
        previous = getattr(self, "disclosure_window", None)
        if previous is not None and previous.winfo_exists():
            previous.lift()
            previous.focus_set()
            return
        window = tk.Toplevel(self, bg=BACKGROUND)
        self.disclosure_window = window
        window.title(self.t("data"))
        window.geometry("780x680")
        window.minsize(540, 420)
        window.transient(self)
        content = tk.Frame(window, bg=BACKGROUND, padx=22, pady=18)
        content.pack(fill="both", expand=True)
        self.label(content, self.t("data"), bold=True, size=19).pack(fill="x", pady=(0, 12))
        body = tk.Frame(content, bg=PAPER)
        body.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(body, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        text = tk.Text(body, wrap="word", relief="flat", bg=PAPER, fg=INK, padx=16, pady=14,
            font=("Helvetica", 12), width=60, height=18, yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=text.yview)
        text.tag_configure("heading", font=("Helvetica", 12, "bold"), spacing1=12, spacing3=6)
        text.tag_configure("body", spacing3=10)
        catalog = DISCLOSURE_CATALOG[self.locale]
        text.insert("end", catalog["intro"]+"\n\n", "body")
        for title, description in catalog["sections"]:
            text.insert("end", title+"\n", "heading")
            text.insert("end", description+"\n\n", "body")
        publication = catalog["publication"]
        text.insert("end", publication["title"]+"\n", "heading")
        for key in ("text", "example", "protection", "status"):
            text.insert("end", publication[key]+"\n\n", "body")
        text.configure(state="disabled")
        self.disclosure_text = text
        note = self.label(content, self.t("data_offline"), color=MUTED, size=10)
        note.pack(fill="x", pady=(12, 8))
        note.bind("<Configure>", lambda event: note.configure(wraplength=max(100, event.width)))
        actions = tk.Frame(content, bg=BACKGROUND)
        actions.pack(fill="x")
        self.button(actions, "data_portal", lambda: self.open_url(self.fields["origin"].get(), "/data")).pack(side="left")
        self.button(actions, "close", window.destroy).pack(side="right")
        window.bind("<Escape>", lambda _event: window.destroy())
        text.focus_set()

    def open_pair(self):
        if self.pairing and self.pairing["expires_at"] <= time.time():
            self.poll_pairing()
            return
        if self.pairing:
            try:
                url = pairing_url(self.pairing["verification_uri"], self.locale)
            except ValueError:
                messagebox.showerror(self.t("title"), self.t("invalid_portal"), parent=self)
                return
            self.open_external(url)

    def open_url(self, origin, path):
        try:
            url = portal_url(origin, path, self.locale)
        except ValueError:
            messagebox.showerror(self.t("title"), self.t("invalid_portal"), parent=self)
            return
        self.open_external(url)

    def account_origin(self):
        return (self.snapshot.get("configuration") or {}).get("origin", self.fields["origin"].get())

    def open_account(self):
        if (self.snapshot.get("configuration") or {}).get("origin"):
            self.open_url(self.account_origin(), "/account")
            return
        if self.account_pending:
            return
        self.account_pending = True
        fallback = self.fields["origin"].get()
        self.feedback.configure(text=self.t("account_opening"))
        def worker():
            try:
                result = self.controller.call("status")
                origin = (result.get("configuration") or {}).get("origin", fallback)
            except Exception:
                origin = fallback
            self.portal_requests.put(origin)
        threading.Thread(target=worker, daemon=True).start()

    def open_external(self, url):
        # Show the address immediately, even if the OS reports success but its
        # default browser never appears. Browser launches cannot block maintenance.
        note = self.show_portal_link(url)
        def worker():
            result = request_browser(url, preview=self.controller.preview)
            self.browser_events.put((note, result["opened"]))
        threading.Thread(target=worker, daemon=True).start()

    def show_portal_link(self, url):
        window = tk.Toplevel(self, bg=BACKGROUND)
        window.title(self.t("portal_link"))
        window.transient(self)
        window.geometry("660x260")
        window.minsize(440, 240)
        content = tk.Frame(window, bg=BACKGROUND, padx=22, pady=18)
        content.pack(fill="both", expand=True)
        note = self.label(content, self.t("browser_opening"), size=12)
        note.pack(fill="x", pady=(0, 14))
        note.bind("<Configure>", lambda event: note.configure(wraplength=max(100, event.width)))
        entry = ttk.Entry(content, width=65)
        entry.insert(0, url)
        entry.configure(state="readonly")
        entry.pack(fill="x", pady=(0, 14))
        actions = tk.Frame(content, bg=BACKGROUND)
        actions.pack(fill="x")
        def copy():
            self.clipboard_clear()
            self.clipboard_append(url)
            self.feedback.configure(text=self.t("link_copied"))
        self.button(actions, "copy_link", copy).pack(side="left")
        self.button(actions, "close", window.destroy).pack(side="right")
        window.bind("<Escape>", lambda _event: window.destroy())
        entry.focus_set()
        entry.selection_range(0, "end")
        self.portal_window, self.portal_entry = window, entry
        return note

    def received_status(self, result):
        self.snapshot = result
        self.show("status")

    def load_status(self):
        def read():
            try:
                return self.controller.call("status")
            except OSError:
                return {"ok": True, "service": "unavailable"}
        self.work(read, self.received_status)

    def page_status(self):
        self.heading("status", "status_detail")
        paired = self.snapshot.get("paired", False)
        enabled = self.snapshot.get("measurements_enabled", False)
        if not self.snapshot:
            state, detail = "status_unknown", "status_unknown_detail"
        elif self.snapshot.get("service") == "unavailable":
            state, detail = "service_unavailable", "service_unavailable_detail"
        elif not self.snapshot.get("configured"):
            state, detail = "setup_needed", "setup_needed_detail"
        elif not self.snapshot.get("contribute"):
            state, detail = "local_ready", "local_ready_detail"
        elif not paired:
            state, detail = "pair_needed", "pair_needed_detail"
        elif enabled:
            state, detail = "tests_active", "tests_active_detail"
        else:
            state, detail = "setup_complete", "setup_complete_detail"
        panel = tk.Frame(self.content, bg=PAPER, padx=16, pady=12)
        panel.pack(fill="x", pady=(0, 12))
        self.label(panel, self.t(state), bold=True, size=15).pack(fill="x")
        problem = self.snapshot.get("problem") or {}
        code = problem.get("code") or self.snapshot.get("code")
        problem_key = self.status_problem(code)
        if not problem_key and paired and not enabled and self.snapshot.get("runner_available") is False:
            problem_key = "no_runner"
        explanation = self.t("last_notice") + " " + self.t(problem_key) if problem_key else self.t(detail)
        self.label(panel, explanation, size=11, width=580,
            color="#705016" if problem_key else MUTED).pack(fill="x", pady=(6, 0))
        zone = (self.snapshot.get("configuration") or {}).get("timezone", self.schedule_timezone)
        self.label(self.content, self.t("schedule_short").format(timezone=zone),
            color=MUTED, size=10).pack(fill="x", pady=(0, 8))
        if self.snapshot and self.snapshot.get("service") != "unavailable":
            next_test = self.status_time(self.snapshot.get("next_due")) if enabled else self.t("next_paused")
            rows = [("service_response", self.status_time(self.snapshot.get("observed_at"))),
                    ("next_test", next_test),
                    ("last_attempt", self.status_time(self.snapshot.get("last_attempt_at"))),
                    ("accepted_records", str(self.snapshot.get("accepted", 0))),
                    ("pending", str(self.snapshot.get("pending", 0)))]
            if self.snapshot.get("quarantined"):
                rows.append(("quarantined", str(self.snapshot["quarantined"])))
            for key, value in rows:
                row = tk.Frame(self.content, bg=PAPER, padx=12, pady=6)
                row.pack(fill="x", pady=(0, 4))
                self.label(row, self.t(key), size=10, width=270).pack(side="left")
                self.label(row, value, bold=True, size=10, width=360).pack(side="right")
        primary = tk.Frame(self.content, bg=BACKGROUND)
        primary.pack(fill="x", pady=(10, 0))
        if self.snapshot.get("contribute") and not paired:
            self.button(primary, "resume_pair", self.begin_pairing, primary=True).pack(side="left")
        elif paired:
            key = "pause" if enabled else "enable"
            activate = self.button(primary, key, lambda action=key: self.schedule(action), primary=True)
            if not enabled and self.snapshot.get("runner_available") is False:
                activate.configure(state="disabled")
            activate.pack(side="left")
        self.button(primary, "refresh_status", self.load_status).pack(side="right")
        secondary = tk.Frame(self.content, bg=BACKGROUND)
        secondary.pack(fill="x", pady=(10, 0))
        for key, command in (("manage", self.configure_existing), ("account", self.open_account),
                             ("copy_info", self.copy_information), ("home", lambda: self.show("welcome"))):
            index = ("manage", "account", "copy_info", "home").index(key)
            button = self.button(secondary, key, command)
            button.configure(font=("Helvetica", 10, "bold"), pady=8, padx=10)
            button.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 8), pady=(0, 6))

    @staticmethod
    def status_problem(code):
        if code in {"test_target_unavailable", "invalid_test_target", "test_target_changed"}:
            return "no_target"
        if code == "iperf3_required":
            return "no_runner"
        if code == "local_or_network_failure":
            return "connection_notice"
        if code == "storage_limit":
            return "storage_notice"
        if code in {"account_suspended", "account_disabled", "client_revoked", "consent_required", "consent_withdrawn",
                    "contribution_consent_required", "terms_acceptance_required", "legal_context_changed",
                    "legal_acceptance_required", "acceptance_required", "documents_changed", "server_rejected",
                    "machine_privacy_not_ready", "invalid_machine_policy", "invalid_machine_permission",
                    "machine_identity_unavailable", "machine_identity_required", "machine_identity_changed",
                    "schedule_update_required", "credential_expired", "invalid_token", "token_revoked"}:
            return "blocked"
        return None

    def copy_information(self):
        text=diagnostic_text(self.snapshot)+"\nTk: "+self.tk.call("package","provide","Tk")
        text+="\nWindow system: "+self.tk.call("tk","windowingsystem")
        self.clipboard_clear()
        self.clipboard_append(text)

    def configure_existing(self):
        if self.busy:
            return
        stored = self.snapshot.get("configuration")
        if stored:
            profile = stored["profile"]
            values = {**profile, "origin": stored["origin"], "country": profile["country_code"]}
            self.schedule_timezone = stored.get("timezone", self.schedule_timezone)
            for key, variable in self.fields.items():
                variable.set(values[key])
            self.form_locale = self.locale
            self.access.set(self.t(profile["access_type"]))
            self.link.set(self.t(profile["link_type"]))
            self.contribute.set(stored["contribute"])
        self.operation = "configure"
        self.show("configure")

    def schedule(self, operation):
        if self.busy:
            return
        if operation == "enable" and not self.ask_confirmation("enable", "enable_confirm"):
            return
        self.work(lambda: self.controller.call(operation), self.received_status)

    def page_remove(self):
        self.heading("remove_title", "remove_detail")
        tk.Checkbutton(self.content, text=self.t("purge"), variable=self.purge, bg=BACKGROUND,
            fg=INK, activebackground=BACKGROUND, wraplength=650, justify="left",
            font=("Helvetica", 12), anchor="w").pack(fill="x", pady=(8, 24))
        self.label(self.content, self.t("revoke_notice"), color=MUTED).pack(fill="x", pady=(0, 20))
        self.button(self.content, "account", self.open_account).pack(anchor="w", pady=(0, 24))
        self.button(self.content, "uninstall", self.uninstall, primary=True).pack(anchor="w", pady=10)
        self.button(self.content, "back", lambda: self.show("welcome")).pack(anchor="w", pady=10)

    def uninstall(self):
        if self.busy:
            return
        if not self.ask_confirmation("uninstall", "remove_confirm"):
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
            if success and isinstance(result, dict) and result.get("ok"):
                try:
                    completed(result)
                except Exception:
                    # A failed UI callback must not kill the event pump forever.
                    messagebox.showerror(self.t("title"), self.t("error"), parent=self)
            else:
                if self.page == "pair" and self.pairing_state == "generating":
                    self.pairing_state = "failed"
                    self.render()
                code = result.get("code") if isinstance(result, dict) else None
                key = "no_target" if code in {"test_target_unavailable", "invalid_test_target", "test_target_changed"} else "no_runner" if code == "iperf3_required" else "blocked" if code else "error"
                messagebox.showerror(self.t("title"), self.t(key), parent=self)
        try:
            while True:
                origin = self.portal_requests.get_nowait()
                self.account_pending = False
                self.open_url(origin, "/account")
        except queue.Empty:
            pass
        try:
            while True:
                note, opened = self.browser_events.get_nowait()
                if note.winfo_exists():
                    note.configure(text=self.t("browser_requested" if opened else "browser_unavailable"))
        except queue.Empty:
            pass
        self.after(100, self.drain)

    def close(self):
        if not self.busy:
            self.destroy()

    def smoke_test(self):
        # Real Tk widgets and all translations; the controller never touches I/O.
        for locale in TEXT:
            self.locale = locale
            confirmation_errors = []
            def dismiss_confirmation():
                popup = self.confirmation_window
                if not popup.winfo_viewable():
                    self.after(20, dismiss_confirmation)
                    return
                try:
                    buttons = [w for child in popup.winfo_children() for w in child.winfo_children() if isinstance(w, tk.Button)]
                    assert {w.cget("text") for w in buttons} == {self.t("yes"), self.t("no")}
                    next(w for w in buttons if w.cget("text") == self.t("no")).invoke()
                except Exception as exc:
                    confirmation_errors.append(exc)
                    popup.destroy()
            self.after(20, dismiss_confirmation)
            assert not self.ask_confirmation("enable", "enable_confirm")
            assert not confirmation_errors, confirmation_errors
            for page in ("welcome", "configure", "pair", "status", "remove"):
                self.show(page)
                self.update()
                assert self.winfo_exists()
                assert CLIENT_VERSION in self.title()
                if page=="configure":
                    assert not {"host", "port", "hours"}.intersection(self.fields)
                    assert self.t("schedule_short").format(timezone=self.schedule_timezone)
                    before = {key: value.get() for key, value in self.fields.items()}
                    self.fields["origin"].set("not a valid server address")
                    before["origin"] = self.fields["origin"].get()
                    self.data_button.invoke()
                    self.update()
                    assert self.disclosure_window.winfo_exists()
                    assert self.disclosure_window.title() == self.t("data")
                    original_window = self.disclosure_window
                    self.data_button.invoke()
                    assert self.disclosure_window is original_window
                    body = self.disclosure_text.get("1.0", "end")
                    for title, description in DISCLOSURE_CATALOG[locale]["sections"]:
                        assert title in body and description in body
                    assert self.disclosure_text.cget("state") == "disabled"
                    self.disclosure_text.yview_moveto(1)
                    self.update()
                    assert self.disclosure_text.yview()[1] == 1.0
                    self.disclosure_window.destroy()
                    assert {key: value.get() for key, value in self.fields.items()} == before
                    self.show_portal_link("https://server.example/data?locale="+locale)
                    self.update()
                    for window in self.winfo_children():
                        if isinstance(window, tk.Toplevel):
                            window.destroy()
        from zoneinfo import ZoneInfo, reset_tzpath, TZPATH
        paths=TZPATH
        try:
            reset_tzpath(())
            ZoneInfo.clear_cache()
            for zone in ("America/Sao_Paulo", "Europe/Madrid", self.schedule_timezone):
                ZoneInfo(zone)
        finally:
            reset_tzpath(paths)
            ZoneInfo.clear_cache()
        import os
        if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted":
            from .machine import machine_identity
            first=machine_identity("https://server.example")
            assert first == machine_identity("https://SERVER.example:443/")
            assert first["machine_id"] != machine_identity("https://another.example")["machine_id"]
            assert len(first["machine_id"]) == 64
        if self.tk.call("tk","windowingsystem")=="x11" and os.environ.get("SPEEDTESTER_INPUT_SMOKE") in {"1", "fallback"}:
            from .input_methods import smoke_dead_keys
            smoke_dead_keys(self)
        self.destroy()
