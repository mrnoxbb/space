import csv
import datetime as dt
import os
import sqlite3
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

DB_PATH = os.path.join(os.path.dirname(__file__), "space.db")

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
        self.root.configure(bg="#0B0B2A")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#0B0B2A")
        style.configure("TLabel", background="#0B0B2A", foreground="#FFD700")
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", background="#101038", foreground="#FFD700")
        style.configure("TButton", background="#1C1C3A", foreground="#FFD700")
        style.map("TButton", background=[("active", "#2A2A5A")])
        style.configure("Treeview", background="#0F0F33", foreground="#FFD700", fieldbackground="#0F0F33")
        style.map("Treeview", background=[("selected", "#2A2A5A")])
        style.configure("TNotebook", background="#0B0B2A")
        style.configure("TNotebook.Tab", background="#1C1C3A", foreground="#FFD700")
        style.map("TNotebook.Tab", background=[("selected", "#2A2A5A")])

    def _build_ui(self):
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=16, pady=12)

        ttk.Label(header, text="Space Venue Control Center", style="Header.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").pack(side="right")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=8)

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
        ttk.Label(self.dashboard_tab, text="Live Stations", style="Header.TLabel").pack(anchor="w", pady=8, padx=12)
        container = ttk.Frame(self.dashboard_tab)
        container.pack(fill="both", expand=True, padx=12)

        for station in STATIONS:
            frame = ttk.Frame(container, padding=12)
            frame.pack(fill="x", pady=6)

            state = StationState(station, self._update_dashboard)
            self.station_states[station["name"]] = state

            name_label = ttk.Label(frame, text=station["name"], font=("Segoe UI", 12, "bold"))
            name_label.grid(row=0, column=0, sticky="w")

            rate_var = tk.DoubleVar(value=station["rate_per_hour"])
            station["rate_var"] = rate_var

            ttk.Label(frame, text="Rate (EGP/hr)").grid(row=0, column=1, padx=8)
            rate_entry = ttk.Entry(frame, textvariable=rate_var, width=10)
            rate_entry.grid(row=0, column=2, padx=4)

            ttk.Label(frame, text="Customer").grid(row=0, column=3, padx=8)
            customer_var = tk.StringVar()
            station["customer_var"] = customer_var
            customer_entry = ttk.Entry(frame, textvariable=customer_var, width=20)
            customer_entry.grid(row=0, column=4)

            state_label = ttk.Label(frame, text="Stopped", foreground="#ff5f5f")
            state_label.grid(row=0, column=5, padx=10)
            station["state_label"] = state_label

            timer_label = ttk.Label(frame, text="00:00:00", font=("Segoe UI", 12, "bold"))
            timer_label.grid(row=1, column=0, sticky="w")
            station["timer_label"] = timer_label

            cost_label = ttk.Label(frame, text="EGP 0.00")
            cost_label.grid(row=1, column=1, sticky="w")
            station["cost_label"] = cost_label

            controls = ttk.Frame(frame)
            controls.grid(row=1, column=3, columnspan=3, sticky="e")
            ttk.Button(controls, text="Start", command=lambda s=state: self._start_station(s)).pack(side="left", padx=4)
            ttk.Button(controls, text="Pause", command=lambda s=state: self._pause_station(s)).pack(side="left", padx=4)
            ttk.Button(controls, text="Stop", command=lambda s=state: self._stop_station(s)).pack(side="left", padx=4)
            ttk.Button(controls, text="Reset", command=lambda s=state: self._reset_station(s)).pack(side="left", padx=4)

        for i in range(6):
            container.columnconfigure(i, weight=1)

    def _build_items(self):
        header = ttk.Frame(self.items_tab)
        header.pack(fill="x", padx=12, pady=8)
        ttk.Label(header, text="Custom Items", style="Header.TLabel").pack(side="left")
        ttk.Button(header, text="Add Item", command=self._add_item).pack(side="right")

        self.items_tree = ttk.Treeview(self.items_tab, columns=("price"), show="headings", height=10)
        self.items_tree.heading("price", text="Price (EGP)")
        self.items_tree.pack(fill="both", expand=True, padx=12)

        controls = ttk.Frame(self.items_tab)
        controls.pack(fill="x", padx=12, pady=8)
        ttk.Button(controls, text="Edit", command=self._edit_item).pack(side="left")
        ttk.Button(controls, text="Delete", command=self._delete_item).pack(side="left", padx=6)
        ttk.Button(controls, text="Sell", command=self._sell_item).pack(side="left", padx=6)

    def _build_cash(self):
        header = ttk.Frame(self.cash_tab)
        header.pack(fill="x", padx=12, pady=8)
        ttk.Label(header, text="Cash Register", style="Header.TLabel").pack(side="left")

        form = ttk.Frame(self.cash_tab)
        form.pack(fill="x", padx=12, pady=6)

        ttk.Label(form, text="Type").grid(row=0, column=0, padx=4, sticky="e")
        self.cash_type = tk.StringVar(value="deposit")
        ttk.Combobox(form, textvariable=self.cash_type, values=["deposit", "withdrawal"], width=12).grid(
            row=0, column=1, padx=4
        )

        ttk.Label(form, text="Amount (EGP)").grid(row=0, column=2, padx=4, sticky="e")
        self.cash_amount = tk.DoubleVar(value=0.0)
        ttk.Entry(form, textvariable=self.cash_amount, width=12).grid(row=0, column=3, padx=4)

        ttk.Label(form, text="Notes").grid(row=0, column=4, padx=4, sticky="e")
        self.cash_notes = tk.StringVar()
        ttk.Entry(form, textvariable=self.cash_notes, width=30).grid(row=0, column=5, padx=4)

        ttk.Button(form, text="Add", command=self._add_cash).grid(row=0, column=6, padx=6)

        self.cash_tree = ttk.Treeview(self.cash_tab, columns=("type", "amount", "notes", "ts"), show="headings")
        for col, label in zip(("type", "amount", "notes", "ts"), ("Type", "Amount", "Notes", "Time")):
            self.cash_tree.heading(col, text=label)
        self.cash_tree.pack(fill="both", expand=True, padx=12, pady=6)

    def _build_reports(self):
        header = ttk.Frame(self.reports_tab)
        header.pack(fill="x", padx=12, pady=8)
        ttk.Label(header, text="Financial Reports", style="Header.TLabel").pack(side="left")
        ttk.Button(header, text="Daily Report", command=lambda: self._build_report("daily")).pack(side="right")
        ttk.Button(header, text="Monthly Report", command=lambda: self._build_report("monthly")).pack(side="right", padx=6)
        ttk.Button(header, text="Export CSV", command=self._export_report).pack(side="right", padx=6)

        self.report_text = tk.Text(self.reports_tab, height=22, bg="#0F0F33", fg="#FFD700", insertbackground="#FFD700")
        self.report_text.pack(fill="both", expand=True, padx=12, pady=8)

    def _build_settings(self):
        ttk.Label(self.settings_tab, text="Settings", style="Header.TLabel").pack(anchor="w", padx=12, pady=8)
        rtl_check = ttk.Checkbutton(
            self.settings_tab,
            text="Enable Arabic (RTL) numerals",
            variable=self.rtl,
            command=self._toggle_rtl,
        )
        rtl_check.pack(anchor="w", padx=12, pady=4)

    def _toggle_rtl(self):
        self._update_dashboard()
        self._refresh_items()
        self._refresh_cash()
        self.status_var.set("Arabic numerals enabled" if self.rtl.get() else "Arabic numerals disabled")

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
                    station["state_label"].configure(text="Paused", foreground="#f6c90e")
                else:
                    station["state_label"].configure(text="Active", foreground="#7CFF8A")
            else:
                station["state_label"].configure(text="Stopped", foreground="#ff5f5f")

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
            for item_id, name, price in conn.execute("SELECT id, name, price FROM items ORDER BY name"):
                label = f"{name}"
                price_text = format_currency(price, self.rtl.get())
                self.items_tree.insert("", "end", iid=str(item_id), values=(price_text,), text=label)
        self.items_tree.configure(displaycolumns=("price",))
        self.items_tree["show"] = "headings"

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
            for tx_id, tx_type, amount, notes, ts in conn.execute(
                "SELECT id, type, amount, notes, ts FROM cash_transactions ORDER BY ts DESC"
            ):
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
