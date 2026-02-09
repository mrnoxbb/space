import csv
import datetime as dt
import os
import sqlite3
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

DB_PATH = os.path.join(os.path.dirname(__file__), "space.db")

COLORS = {
    "primary": "#1E1E2F",
    "secondary": "#FFD700",
    "background": "#101038",
    "text": "#FFFFFF",
    "button": "#1C1C3A",
    "button_active": "#2A2A5A",
    "panel": "#151545",
    "accent_red": "#ff5f5f",
    "accent_green": "#7CFF8A",
    "accent_yellow": "#f6c90e",
}

STATIONS = [
    {"name": "Table 1", "type": "table", "rate_per_hour": 60.0},
    {"name": "Table 2", "type": "table", "rate_per_hour": 60.0},
    {"name": "Table 3", "type": "table", "rate_per_hour": 60.0},
    {"name": "PlayStation 1", "type": "ps", "rate_per_hour": 40.0},
    {"name": "PlayStation 2", "type": "ps", "rate_per_hour": 40.0},
]


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS item_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                total REAL NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cash_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                notes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_name TEXT NOT NULL,
                customer_name TEXT,
                start_ts TEXT NOT NULL,
                end_ts TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                rate_per_hour REAL NOT NULL,
                cost REAL NOT NULL
            )
            """
        )


def format_currency(amount, rtl=False):
    formatted = f"EGP {amount:,.2f}"
    if rtl:
        return to_arabic_numerals(formatted)
    return formatted


def to_arabic_numerals(text):
    arabic_digits = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    return text.translate(arabic_digits)


def now_iso():
    return dt.datetime.now().isoformat(timespec="seconds")


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            self.tip,
            text=self.text,
            padding=6,
            background=COLORS["primary"],
            foreground=COLORS["secondary"],
            relief="solid",
            borderwidth=1,
        )
        label.pack()

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class StationState:
    def __init__(self, station, on_update):
        self.station = station
        self.on_update = on_update
        self.running = False
        self.paused = False
        self.start_ts = None
        self.elapsed = 0
        self.customer_name = ""

    def start(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        self.start_ts = time.time()
        self.on_update()

    def pause(self):
        if not self.running:
            return
        if not self.paused:
            self.elapsed += time.time() - self.start_ts
            self.paused = True
        else:
            self.start_ts = time.time()
            self.paused = False
        self.on_update()

    def stop(self):
        if not self.running:
            return
        if not self.paused:
            self.elapsed += time.time() - self.start_ts
        self.running = False
        self.paused = False
        self.on_update()

    def reset(self):
        self.running = False
        self.paused = False
        self.start_ts = None
        self.elapsed = 0
        self.customer_name = ""
        self.on_update()

    def current_elapsed(self):
        if self.running and not self.paused:
            return self.elapsed + (time.time() - self.start_ts)
        return self.elapsed


class SpaceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Space Venue Manager")
        self.root.geometry("1200x720")
        self.rtl = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.station_states = {}

        self._setup_style()
        self._build_ui()
        self._refresh_items()
        self._refresh_cash()
        self._schedule_tick()

    def _setup_style(self):
        self.root.configure(bg=COLORS["background"])
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"])
        style.configure("Card.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground=COLORS["secondary"])
        style.configure("Status.TLabel", background=COLORS["primary"], foreground=COLORS["secondary"], padding=6)
        style.configure("TButton", background=COLORS["button"], foreground=COLORS["secondary"], padding=10)
        style.map("TButton", background=[("active", COLORS["button_active"])])
        style.configure(
            "Treeview",
            background=COLORS["primary"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["primary"],
            rowheight=26,
        )
        style.map("Treeview", background=[("selected", COLORS["button_active"])])
        style.configure("TNotebook", background=COLORS["background"])
        style.configure("TNotebook.Tab", background=COLORS["button"], foreground=COLORS["secondary"], padding=(12, 8))
        style.map("TNotebook.Tab", background=[("selected", COLORS["button_active"])])

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(16, 12))
        header.pack(fill="x")

        ttk.Label(header, text="Space Venue Control Center", style="Header.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").pack(side="right")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=16, pady=12)

        self.dashboard_tab = ttk.Frame(notebook)
        self.items_tab = ttk.Frame(notebook)
        self.cash_tab = ttk.Frame(notebook)
        self.reports_tab = ttk.Frame(notebook)
        self.settings_tab = ttk.Frame(notebook)

        notebook.add(self.dashboard_tab, text="Dashboard")
        notebook.add(self.items_tab, text="Items")
        notebook.add(self.cash_tab, text="Cash Register")
        notebook.add(self.reports_tab, text="Reports")
        notebook.add(self.settings_tab, text="Settings")

        self._build_dashboard()
        self._build_items()
        self._build_cash()
        self._build_reports()
        self._build_settings()

    def _build_dashboard(self):
        ttk.Label(self.dashboard_tab, text="Live Stations", style="Header.TLabel").pack(anchor="w", pady=8, padx=16)
        container = ttk.Frame(self.dashboard_tab, padding=(8, 4))
        container.pack(fill="both", expand=True, padx=12, pady=8)

        for station in STATIONS:
            frame = ttk.Frame(container, padding=16, style="Card.TFrame")
            frame.pack(fill="x", pady=10)

            state = StationState(station, self._update_dashboard)
            self.station_states[station["name"]] = state

            name_label = ttk.Label(frame, text=station["name"], font=("Segoe UI", 12, "bold"), style="Card.TLabel")
            name_label.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))

            rate_var = tk.DoubleVar(value=station["rate_per_hour"])
            station["rate_var"] = rate_var

            ttk.Label(frame, text="Rate (EGP/hr)", style="Card.TLabel").grid(row=0, column=1, padx=8, pady=(0, 6))
            rate_entry = ttk.Entry(frame, textvariable=rate_var, width=10)
            rate_entry.grid(row=0, column=2, padx=6, pady=(0, 6))

            ttk.Label(frame, text="Customer", style="Card.TLabel").grid(row=0, column=3, padx=8, pady=(0, 6))
            customer_var = tk.StringVar()
            station["customer_var"] = customer_var
            customer_entry = ttk.Entry(frame, textvariable=customer_var, width=20)
            customer_entry.grid(row=0, column=4, padx=6, pady=(0, 6))

            state_label = ttk.Label(
                frame,
                text="Stopped",
                foreground=COLORS["accent_red"],
                style="Card.TLabel",
            )
            state_label.grid(row=0, column=5, padx=12, pady=(0, 6))
            station["state_label"] = state_label

            timer_label = ttk.Label(frame, text="00:00:00", font=("Segoe UI", 12, "bold"), style="Card.TLabel")
            timer_label.grid(row=1, column=0, sticky="w", padx=(0, 8))
            station["timer_label"] = timer_label

            cost_label = ttk.Label(frame, text="EGP 0.00", style="Card.TLabel")
            cost_label.grid(row=1, column=1, sticky="w", padx=(0, 8))
            station["cost_label"] = cost_label

            controls = ttk.Frame(frame, style="Card.TFrame")
            controls.grid(row=1, column=3, columnspan=3, sticky="e", pady=(4, 0))
            start_btn = ttk.Button(controls, text="▶ Start", command=lambda s=state: self._start_station(s))
            pause_btn = ttk.Button(controls, text="⏸ Pause", command=lambda s=state: self._pause_station(s))
            stop_btn = ttk.Button(controls, text="⏹ Stop", command=lambda s=state: self._stop_station(s))
            reset_btn = ttk.Button(controls, text="⟲ Reset", command=lambda s=state: self._reset_station(s))
            for btn in (start_btn, pause_btn, stop_btn, reset_btn):
                btn.pack(side="left", padx=6)
            ToolTip(start_btn, "Start session timer")
            ToolTip(pause_btn, "Pause or resume session")
            ToolTip(stop_btn, "Stop session and save")
            ToolTip(reset_btn, "Clear timer and customer info")

        for i in range(6):
            container.columnconfigure(i, weight=1)

    def _build_items(self):
        header = ttk.Frame(self.items_tab, padding=(12, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Custom Items", style="Header.TLabel").pack(side="left")
        ttk.Button(header, text="Add Item", command=self._add_item).pack(side="right")

        filter_row = ttk.Frame(self.items_tab, padding=(12, 4))
        filter_row.pack(fill="x")
        ttk.Label(filter_row, text="Search").pack(side="left")
        self.item_search = tk.StringVar()
        search_entry = ttk.Entry(filter_row, textvariable=self.item_search, width=24)
        search_entry.pack(side="left", padx=6)
        search_entry.bind("<KeyRelease>", lambda _event: self._refresh_items())

        tree_frame = ttk.Frame(self.items_tab, padding=(12, 4))
        tree_frame.pack(fill="both", expand=True)
        self.items_tree = ttk.Treeview(tree_frame, columns=("name", "price"), show="headings", height=10)
        self.items_tree.heading("name", text="Item", command=lambda: self._sort_tree(self.items_tree, "name"))
        self.items_tree.heading("price", text="Price (EGP)", command=lambda: self._sort_tree(self.items_tree, "price"))
        self.items_tree.column("name", width=240)
        self.items_tree.column("price", width=120, anchor="e")
        items_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.items_tree.yview)
        self.items_tree.configure(yscrollcommand=items_scroll.set)
        self.items_tree.pack(side="left", fill="both", expand=True)
        items_scroll.pack(side="right", fill="y")

        controls = ttk.Frame(self.items_tab, padding=(12, 8))
        controls.pack(fill="x")
        edit_btn = ttk.Button(controls, text="Edit", command=self._edit_item)
        delete_btn = ttk.Button(controls, text="Delete", command=self._delete_item)
        sell_btn = ttk.Button(controls, text="Sell", command=self._sell_item)
        edit_btn.pack(side="left")
        delete_btn.pack(side="left", padx=6)
        sell_btn.pack(side="left", padx=6)
        ToolTip(edit_btn, "Edit selected item")
        ToolTip(delete_btn, "Delete selected item")
        ToolTip(sell_btn, "Record a sale for selected item")

    def _build_cash(self):
        header = ttk.Frame(self.cash_tab, padding=(12, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Cash Register", style="Header.TLabel").pack(side="left")

        form = ttk.Frame(self.cash_tab, padding=(12, 6))
        form.pack(fill="x")

        ttk.Label(form, text="Type").grid(row=0, column=0, padx=6, sticky="e")
        self.cash_type = tk.StringVar(value="deposit")
        ttk.Combobox(form, textvariable=self.cash_type, values=["deposit", "withdrawal"], width=12).grid(
            row=0, column=1, padx=6
        )

        ttk.Label(form, text="Amount (EGP)").grid(row=0, column=2, padx=6, sticky="e")
        self.cash_amount = tk.DoubleVar(value=0.0)
        ttk.Entry(form, textvariable=self.cash_amount, width=12).grid(row=0, column=3, padx=6)

        ttk.Label(form, text="Notes").grid(row=0, column=4, padx=6, sticky="e")
        self.cash_notes = tk.StringVar()
        ttk.Entry(form, textvariable=self.cash_notes, width=30).grid(row=0, column=5, padx=6)

        add_btn = ttk.Button(form, text="Add", command=self._add_cash)
        add_btn.grid(row=0, column=6, padx=8)
        ToolTip(add_btn, "Record a cash deposit or withdrawal")

        filter_row = ttk.Frame(self.cash_tab, padding=(12, 4))
        filter_row.pack(fill="x")
        ttk.Label(filter_row, text="Search").pack(side="left")
        self.cash_search = tk.StringVar()
        cash_entry = ttk.Entry(filter_row, textvariable=self.cash_search, width=24)
        cash_entry.pack(side="left", padx=6)
        cash_entry.bind("<KeyRelease>", lambda _event: self._refresh_cash())

        cash_frame = ttk.Frame(self.cash_tab, padding=(12, 4))
        cash_frame.pack(fill="both", expand=True)
        self.cash_tree = ttk.Treeview(cash_frame, columns=("type", "amount", "notes", "ts"), show="headings")
        for col, label in zip(("type", "amount", "notes", "ts"), ("Type", "Amount", "Notes", "Time")):
            self.cash_tree.heading(col, text=label, command=lambda c=col: self._sort_tree(self.cash_tree, c))
        self.cash_tree.column("type", width=100)
        self.cash_tree.column("amount", width=120, anchor="e")
        self.cash_tree.column("notes", width=260)
        self.cash_tree.column("ts", width=160)
        cash_scroll = ttk.Scrollbar(cash_frame, orient="vertical", command=self.cash_tree.yview)
        self.cash_tree.configure(yscrollcommand=cash_scroll.set)
        self.cash_tree.pack(side="left", fill="both", expand=True)
        cash_scroll.pack(side="right", fill="y")

    def _build_reports(self):
        header = ttk.Frame(self.reports_tab, padding=(12, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Financial Reports", style="Header.TLabel").pack(side="left")
        ttk.Button(header, text="Daily Report", command=lambda: self._build_report("daily")).pack(side="right")
        ttk.Button(header, text="Monthly Report", command=lambda: self._build_report("monthly")).pack(side="right", padx=6)
        ttk.Button(header, text="Export CSV", command=self._export_report).pack(side="right", padx=6)

        report_frame = ttk.Frame(self.reports_tab, padding=(12, 4))
        report_frame.pack(fill="both", expand=True)
        self.report_text = tk.Text(
            report_frame,
            height=22,
            bg=COLORS["primary"],
            fg=COLORS["text"],
            insertbackground=COLORS["secondary"],
        )
        report_scroll = ttk.Scrollbar(report_frame, orient="vertical", command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=report_scroll.set)
        self.report_text.pack(side="left", fill="both", expand=True)
        report_scroll.pack(side="right", fill="y")

    def _build_settings(self):
        ttk.Label(self.settings_tab, text="Settings", style="Header.TLabel").pack(anchor="w", padx=16, pady=12)
        rtl_check = ttk.Checkbutton(
            self.settings_tab,
            text="Enable Arabic (RTL) numerals",
            variable=self.rtl,
            command=self._toggle_rtl,
        )
        rtl_check.pack(anchor="w", padx=16, pady=6)

    def _toggle_rtl(self):
        self._update_dashboard()
        self._refresh_items()
        self._refresh_cash()
        self.status_var.set("Arabic numerals enabled" if self.rtl.get() else "Arabic numerals disabled")

    def _sort_tree(self, tree, col):
        data = [(tree.set(item, col), item) for item in tree.get_children("")]
        try:
            data.sort(key=lambda item: float(item[0].replace(",", "").replace("EGP", "").strip()))
        except ValueError:
            data.sort(key=lambda item: item[0].lower())
        for index, (_value, item) in enumerate(data):
            tree.move(item, "", index)

    def _update_dashboard(self):
        for station in STATIONS:
            state = self.station_states[station["name"]]
            station["customer_var"].set(station["customer_var"].get())
            elapsed = state.current_elapsed()
            timer_text = time.strftime("%H:%M:%S", time.gmtime(elapsed))
            cost = (elapsed / 3600) * station["rate_var"].get()
            station["timer_label"].configure(text=timer_text)
            station["cost_label"].configure(text=format_currency(cost, self.rtl.get()))
            if state.running:
                if state.paused:
                    station["state_label"].configure(text="Paused", foreground=COLORS["accent_yellow"])
                else:
                    station["state_label"].configure(text="Active", foreground=COLORS["accent_green"])
            else:
                station["state_label"].configure(text="Stopped", foreground=COLORS["accent_red"])

    def _schedule_tick(self):
        self._update_dashboard()
        self.root.after(1000, self._schedule_tick)

    def _start_station(self, state):
        state.customer_name = state.station["customer_var"].get()
        state.start()
        self.status_var.set(f"Started {state.station['name']}")

    def _pause_station(self, state):
        state.pause()
        self.status_var.set(f"Paused {state.station['name']}")

    def _stop_station(self, state):
        if not state.running:
            return
        state.stop()
        elapsed = state.current_elapsed()
        cost = (elapsed / 3600) * state.station["rate_var"].get()
        self._save_session(state.station["name"], state.customer_name, elapsed, state.station["rate_var"].get(), cost)
        self.status_var.set(f"Stopped {state.station['name']} | {format_currency(cost, self.rtl.get())}")

    def _reset_station(self, state):
        state.reset()
        self.status_var.set(f"Reset {state.station['name']}")

    def _save_session(self, station_name, customer_name, elapsed, rate, cost):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO sessions (station_name, customer_name, start_ts, end_ts, duration_seconds, rate_per_hour, cost)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    station_name,
                    customer_name,
                    now_iso(),
                    now_iso(),
                    int(elapsed),
                    rate,
                    cost,
                ),
            )
        self._refresh_reports_if_visible()

    def _refresh_reports_if_visible(self):
        if self.report_text.get("1.0", tk.END).strip():
            self._build_report("daily")

    def _refresh_items(self):
        for row in self.items_tree.get_children():
            self.items_tree.delete(row)
        with sqlite3.connect(DB_PATH) as conn:
            query = "SELECT id, name, price FROM items ORDER BY name"
            rows = conn.execute(query).fetchall()
            search_term = self.item_search.get().strip().lower() if hasattr(self, "item_search") else ""
            for item_id, name, price in rows:
                if search_term and search_term not in name.lower():
                    continue
                price_text = format_currency(price, self.rtl.get())
                self.items_tree.insert("", "end", iid=str(item_id), values=(name, price_text))

    def _add_item(self):
        ItemDialog(self.root, "Add Item", self._save_new_item)

    def _edit_item(self):
        selection = self.items_tree.selection()
        if not selection:
            messagebox.showwarning("Select item", "Please select an item to edit.")
            return
        item_id = int(selection[0])
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT name, price FROM items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return
        ItemDialog(self.root, "Edit Item", lambda n, p: self._update_item(item_id, n, p), row)

    def _delete_item(self):
        selection = self.items_tree.selection()
        if not selection:
            messagebox.showwarning("Select item", "Please select an item to delete.")
            return
        item_id = int(selection[0])
        if not messagebox.askyesno("Confirm", "Delete selected item?"):
            return
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self._refresh_items()

    def _save_new_item(self, name, price):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO items (name, price) VALUES (?, ?)", (name, price))
        self._refresh_items()

    def _update_item(self, item_id, name, price):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE items SET name = ?, price = ? WHERE id = ?", (name, price, item_id))
        self._refresh_items()

    def _sell_item(self):
        selection = self.items_tree.selection()
        if not selection:
            messagebox.showwarning("Select item", "Please select an item to sell.")
            return
        item_id = int(selection[0])
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT name, price FROM items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return
        SaleDialog(self.root, row[0], row[1], lambda qty: self._record_sale(item_id, row[1], qty))

    def _record_sale(self, item_id, price, qty):
        total = price * qty
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO item_sales (ts, item_id, qty, total) VALUES (?, ?, ?, ?)",
                (now_iso(), item_id, qty, total),
            )
        self.status_var.set(f"Sale recorded: {format_currency(total, self.rtl.get())}")
        self._refresh_reports_if_visible()

    def _add_cash(self):
        amount = self.cash_amount.get()
        if amount <= 0:
            messagebox.showwarning("Invalid amount", "Amount must be greater than zero.")
            return
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO cash_transactions (ts, type, amount, notes) VALUES (?, ?, ?, ?)",
                (now_iso(), self.cash_type.get(), amount, self.cash_notes.get()),
            )
        self.cash_amount.set(0.0)
        self.cash_notes.set("")
        self._refresh_cash()
        self._refresh_reports_if_visible()

    def _refresh_cash(self):
        for row in self.cash_tree.get_children():
            self.cash_tree.delete(row)
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, type, amount, notes, ts FROM cash_transactions ORDER BY ts DESC"
            ).fetchall()
            search_term = self.cash_search.get().strip().lower() if hasattr(self, "cash_search") else ""
            for tx_id, tx_type, amount, notes, ts in rows:
                searchable = f"{tx_type} {notes or ''} {ts}".lower()
                if search_term and search_term not in searchable:
                    continue
                self.cash_tree.insert(
                    "", "end", iid=str(tx_id), values=(tx_type, format_currency(amount, self.rtl.get()), notes, ts)
                )

    def _build_report(self, mode):
        today = dt.date.today()
        if mode == "daily":
            start = dt.datetime.combine(today, dt.time.min)
            end = dt.datetime.combine(today, dt.time.max)
            title = f"Daily Report - {today.isoformat()}"
        else:
            start = dt.datetime(today.year, today.month, 1)
            next_month = start + dt.timedelta(days=32)
            end = dt.datetime(next_month.year, next_month.month, 1) - dt.timedelta(seconds=1)
            title = f"Monthly Report - {today.strftime('%B %Y')}"

        with sqlite3.connect(DB_PATH) as conn:
            sessions_total = conn.execute(
                "SELECT COALESCE(SUM(cost), 0) FROM sessions WHERE start_ts BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchone()[0]
            sales_total = conn.execute(
                "SELECT COALESCE(SUM(total), 0) FROM item_sales WHERE ts BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchone()[0]
            cash_total = conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN type = 'deposit' THEN amount ELSE -amount END), 0) FROM cash_transactions"
                " WHERE ts BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchone()[0]

        self.report_text.delete("1.0", tk.END)
        self.report_text.insert(tk.END, f"{title}\n")
        self.report_text.insert(tk.END, "=" * 40 + "\n")
        self.report_text.insert(tk.END, f"Session Revenue: {format_currency(sessions_total, self.rtl.get())}\n")
        self.report_text.insert(tk.END, f"Item Sales: {format_currency(sales_total, self.rtl.get())}\n")
        self.report_text.insert(tk.END, f"Cash Net: {format_currency(cash_total, self.rtl.get())}\n")
        self.report_text.insert(tk.END, "=" * 40 + "\n")
        self.report_text.insert(
            tk.END,
            f"Total Revenue: {format_currency(sessions_total + sales_total, self.rtl.get())}\n",
        )

    def _export_report(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with sqlite3.connect(DB_PATH) as conn, open(path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Section", "Amount (EGP)"])
            sessions_total = conn.execute("SELECT COALESCE(SUM(cost), 0) FROM sessions").fetchone()[0]
            sales_total = conn.execute("SELECT COALESCE(SUM(total), 0) FROM item_sales").fetchone()[0]
            cash_total = conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN type = 'deposit' THEN amount ELSE -amount END), 0) FROM cash_transactions"
            ).fetchone()[0]
            writer.writerow(["Sessions", f"{sessions_total:.2f}"])
            writer.writerow(["Item Sales", f"{sales_total:.2f}"])
            writer.writerow(["Cash Net", f"{cash_total:.2f}"])
        self.status_var.set(f"Report exported to {path}")


class ItemDialog(tk.Toplevel):
    def __init__(self, parent, title, on_save, row=None):
        super().__init__(parent)
        self.title(title)
        self.on_save = on_save
        self.configure(bg="#0B0B2A")
        self.resizable(False, False)

        ttk.Label(self, text="Name").grid(row=0, column=0, padx=8, pady=6)
        self.name_var = tk.StringVar(value=row[0] if row else "")
        ttk.Entry(self, textvariable=self.name_var).grid(row=0, column=1, padx=8, pady=6)

        ttk.Label(self, text="Price (EGP)").grid(row=1, column=0, padx=8, pady=6)
        self.price_var = tk.DoubleVar(value=row[1] if row else 0.0)
        ttk.Entry(self, textvariable=self.price_var).grid(row=1, column=1, padx=8, pady=6)

        ttk.Button(self, text="Save", command=self._save).grid(row=2, column=0, columnspan=2, pady=10)

    def _save(self):
        name = self.name_var.get().strip()
        price = self.price_var.get()
        if not name or price <= 0:
            messagebox.showwarning("Invalid", "Please enter valid name and price.")
            return
        self.on_save(name, price)
        self.destroy()


class SaleDialog(tk.Toplevel):
    def __init__(self, parent, item_name, price, on_sale):
        super().__init__(parent)
        self.title("Sell Item")
        self.on_sale = on_sale
        self.configure(bg="#0B0B2A")
        self.resizable(False, False)

        ttk.Label(self, text=f"Item: {item_name}").grid(row=0, column=0, columnspan=2, padx=8, pady=6)
        ttk.Label(self, text=f"Price: EGP {price:.2f}").grid(row=1, column=0, columnspan=2, padx=8, pady=6)

        ttk.Label(self, text="Qty").grid(row=2, column=0, padx=8, pady=6)
        self.qty_var = tk.IntVar(value=1)
        ttk.Entry(self, textvariable=self.qty_var, width=6).grid(row=2, column=1, padx=8, pady=6)

        ttk.Button(self, text="Confirm", command=self._confirm).grid(row=3, column=0, columnspan=2, pady=10)

    def _confirm(self):
        qty = self.qty_var.get()
        if qty <= 0:
            messagebox.showwarning("Invalid", "Quantity must be at least 1.")
            return
        self.on_sale(qty)
        self.destroy()


if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = SpaceApp(root)
    root.mainloop()
