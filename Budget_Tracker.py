__version__ = "0.84-beta"

import customtkinter as ctk
import sqlite3
from tkinter import messagebox, ttk, Menu, filedialog, simpledialog
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import calendar
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkcalendar import DateEntry
import sys
import os
import json
from contextlib import contextmanager

# ------------------------------------------------------------------
# Multi-budget support
# ------------------------------------------------------------------
CURRENT_DB = "budget.db"

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_db_path(filename=None):
    if filename is None:
        filename = CURRENT_DB
    return os.path.join(get_base_path(), filename)

def get_last_budget_file():
    return os.path.join(get_base_path(), "last_budget.txt")

def save_last_budget(name):
    try:
        with open(get_last_budget_file(), "w") as f:
            f.write(name)
    except:
        pass

def load_last_budget():
    try:
        with open(get_last_budget_file(), "r") as f:
            name = f.read().strip()
            if name and os.path.exists(get_db_path(name)):
                return name
    except:
        pass
    return None

@contextmanager
def get_db():
    conn = sqlite3.connect(get_db_path())
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS inputs (
                id INTEGER PRIMARY KEY,
                current_balance REAL,
                as_of_date TEXT,
                buffer REAL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL,
                due_day INTEGER,
                category TEXT,
                frequency TEXT,
                month INTEGER,
                anchor_date TEXT,
                sort_order INTEGER DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS incomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT,
                amount REAL,
                hours REAL,
                frequency TEXT,
                due_day INTEGER,
                month INTEGER,
                notes TEXT,
                sort_order INTEGER DEFAULT 0,
                is_primary INTEGER DEFAULT 0,
                anchor_date TEXT,
                interval_days INTEGER
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS paid_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                description TEXT,
                UNIQUE(date, description)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)

        cur.execute("SELECT COUNT(*) FROM categories")
        if cur.fetchone()[0] == 0:
            defaults = [
                "Housing", "Utilities", "Food", "Transportation",
                "Entertainment", "Health", "Insurance", "Subscriptions",
                "Personal", "Other", "Uncategorized"
            ]
            for d in defaults:
                cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (d,))

        for table, column, definition in [
            ("bills", "anchor_date", "TEXT"),
            ("bills", "sort_order", "INTEGER DEFAULT 0"),
            ("incomes", "is_primary", "INTEGER DEFAULT 0"),
            ("incomes", "anchor_date", "TEXT"),
            ("incomes", "interval_days", "INTEGER"),
            ("incomes", "sort_order", "INTEGER DEFAULT 0"),
        ]:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except:
                pass

        try:
            cur.execute("PRAGMA table_info(inputs)")
            cols = [r[1] for r in cur.fetchall()]
            if "paycheck_amount" in cols:
                cur.execute("""SELECT current_balance, as_of_date, paycheck_amount,
                                      next_pay_date, pay_interval, buffer, pay_schedule
                               FROM inputs LIMIT 1""")
                row = cur.fetchone()
                if row and row[2]:
                    cur.execute("SELECT COUNT(*) FROM incomes WHERE is_primary=1")
                    if cur.fetchone()[0] == 0:
                        amount = float(row[2] or 0)
                        next_d = row[3]
                        interval = int(row[4] or 14)
                        schedule = row[6] if len(row) > 6 and row[6] else "Days Interval"
                        cur.execute("""INSERT INTO incomes
                            (name, type, amount, hours, frequency, notes, sort_order,
                             is_primary, anchor_date, interval_days)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            ("Primary Paycheck", "Primary Paycheck", amount, None,
                             schedule, "Migrated", 0, 1, next_d, interval))

                    cur.execute("""CREATE TABLE inputs_new (
                        id INTEGER PRIMARY KEY,
                        current_balance REAL,
                        as_of_date TEXT,
                        buffer REAL)""")
                    cur.execute("INSERT INTO inputs_new (current_balance, as_of_date, buffer) VALUES (?,?,?)",
                                (row[0], row[1], row[5] if len(row) > 5 else 500))
                    cur.execute("DROP TABLE inputs")
                    cur.execute("ALTER TABLE inputs_new RENAME TO inputs")
        except Exception:
            pass

        conn.commit()

# ------------------------------------------------------------------
# Launcher
# ------------------------------------------------------------------
class BudgetLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Select Budget")
        self.geometry("460x420")
        self.resizable(False, False)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        ctk.CTkLabel(self, text="Personal Budget Tracker",
                     font=ctk.CTkFont(family="Verdana", size=20, weight="bold")).pack(pady=(20, 6))
        ctk.CTkLabel(self, text="Choose a budget file or create a new one",
                     font=ctk.CTkFont(family="Verdana", size=13)).pack(pady=(0, 15))

        self.list_frame = ctk.CTkScrollableFrame(self, width=400, height=220)
        self.list_frame.pack(pady=5)

        self.selected_var = ctk.StringVar()
        self.refresh_list()

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(btn_frame, text="Open Selected", width=150, height=36,
                      command=self.open_selected,
                      font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Create New…", width=150, height=36,
                      command=self.create_new,
                      font=ctk.CTkFont(family="Verdana", size=13)).pack(side="left", padx=8)

    def refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        files = sorted([f for f in os.listdir(get_base_path()) if f.lower().endswith(".db")])
        if not files:
            ctk.CTkLabel(self.list_frame, text="No budget files found.\nClick “Create New…” to start.",
                         font=ctk.CTkFont(family="Verdana", size=13)).pack(pady=40)
            return

        self.selected_var.set(files[0])
        for f in files:
            ctk.CTkRadioButton(self.list_frame, text=f, variable=self.selected_var, value=f,
                               font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w", padx=20, pady=4)

    def open_selected(self):
        global CURRENT_DB
        name = self.selected_var.get()
        if not name:
            messagebox.showwarning("Select a file", "Please select a budget file.")
            return
        CURRENT_DB = name
        save_last_budget(name)
        self.destroy()
        app = BudgetApp()
        app.mainloop()

    def create_new(self):
        name = simpledialog.askstring("New Budget", "Enter a name for the new budget\n(without .db extension):", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if not name.lower().endswith(".db"):
            name += ".db"

        global CURRENT_DB
        CURRENT_DB = name
        open(get_db_path(name), "a").close()
        init_database()
        save_last_budget(name)
        self.destroy()
        app = BudgetApp()
        app.mainloop()

# ------------------------------------------------------------------
# Main Application
# ------------------------------------------------------------------
MONTH_COLORS_LIGHT = [
    "#d0e2f3", "#c8e6c9", "#dcedc8", "#ffe0b2",
    "#e1bee7", "#b3e5fc", "#ffccbc", "#c5cae9",
    "#d7ccc8", "#f8bbd0", "#b2dfdb", "#fff9c4"
]

MONTH_COLORS_DARK = [
    "#1e3a5f", "#1b4332", "#3d4a1f", "#5c3d1e",
    "#4a1e4a", "#1e3a5c", "#5c3d1e", "#1e2a4a",
    "#1b4332", "#5c1e1e", "#2e1e5c", "#4a4a1e"
]

SCHEDULE_OPTIONS = [
    "Days Interval",
    "Semi-monthly (14th & 28th)",
    "Semi-monthly (1st & 15th)",
    "Semi-monthly (15th & Last)"
]

NORMAL_FREQ_OPTIONS = ["Bi-weekly", "Monthly", "Quarterly", "Weekly"]

QUARTER_OPTIONS = [
    "Jan / Apr / Jul / Oct",
    "Feb / May / Aug / Nov",
    "Mar / Jun / Sep / Dec"
]

QUARTER_MAP = {
    "Jan / Apr / Jul / Oct": 1,
    "Feb / May / Aug / Nov": 2,
    "Mar / Jun / Sep / Dec": 3
}

REVERSE_QUARTER_MAP = {v: k for k, v in QUARTER_MAP.items()}

class BudgetApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Personal Budget Tracker — {CURRENT_DB}  (v{__version__})")
        self.geometry("1280x850")
        self.minsize(1100, 720)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.projection_win = None
        self.editing_id = None
        self.editing_income_id = None
        self.safe_period = "next_pay"
        self.safe_inclusive = False

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        menubar = Menu(self)
        self.configure(menu=menubar)
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Switch Budget…", command=self.switch_budget)
        file_menu.add_command(label="New Budget…", command=self.new_budget)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)

        init_database()
        self.load_safe_settings()
        self.create_widgets()
        self.apply_theme("Dark")
        self.load_inputs()
        self.load_bills()
        self.load_incomes()
        self.on_frequency_change("Monthly")
        self.on_income_type_change("Fixed")
        self.update_dashboard()

    def load_safe_settings(self):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM settings WHERE key='safe_period'")
                row = cur.fetchone()
                if row and row[0] in ("next_pay", "eom"):
                    self.safe_period = row[0]
                cur.execute("SELECT value FROM settings WHERE key='safe_inclusive'")
                row = cur.fetchone()
                if row:
                    self.safe_inclusive = (row[0] == "1")
        except Exception:
            pass

    def save_safe_settings(self):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                            ("safe_period", self.safe_period))
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                            ("safe_inclusive", "1" if self.safe_inclusive else "0"))
                conn.commit()
        except Exception:
            pass

    def switch_budget(self):
        path = filedialog.askopenfilename(
            title="Select Budget File",
            initialdir=get_base_path(),
            filetypes=[("Budget files", "*.db"), ("All files", "*.*")]
        )
        if not path:
            return
        name = os.path.basename(path)
        self._load_budget(name)

    def new_budget(self):
        name = simpledialog.askstring("New Budget", "Enter a name for the new budget\n(without .db extension):", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if not name.lower().endswith(".db"):
            name += ".db"
        open(get_db_path(name), "a").close()
        self._load_budget(name)

    def _load_budget(self, name):
        global CURRENT_DB
        if self.projection_win and self.projection_win.winfo_exists():
            self.projection_win.destroy()
            self.projection_win = None

        CURRENT_DB = name
        save_last_budget(name)
        init_database()
        self.load_safe_settings()
        self.title(f"Personal Budget Tracker — {CURRENT_DB}  (v{__version__})")
        self.load_inputs()
        self.load_bills()
        self.load_incomes()
        self.bill_category.configure(values=self.get_categories())
        self.update_dashboard()
        self.status_label.configure(text=f"Loaded {CURRENT_DB}", text_color="#9ece6a")

    def on_closing(self):
        try:
            self.save_column_widths(self.tree, "bills_col_widths")
            self.save_column_widths(self.inc_tree, "incomes_col_widths")
            self.save_safe_settings()
        except:
            pass
        self.destroy()

    def save_column_widths(self, tree, key):
        widths = {}
        for col in tree["columns"]:
            widths[col] = tree.column(col, "width")
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, json.dumps(widths)))
            conn.commit()

    def load_column_widths(self, tree, key, defaults):
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()

        if row:
            try:
                saved = json.loads(row[0])
                for col, width in saved.items():
                    if col in tree["columns"]:
                        tree.column(col, width=int(width))
                return
            except:
                pass

        for col, width in defaults.items():
            tree.column(col, width=width)

    def create_widgets(self):
        # Top Bar
        top = ctk.CTkFrame(self, height=52, corner_radius=0, fg_color=("#d1d5d8", "#2b2b2b"))
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="Personal Budget Tracker",
                     font=ctk.CTkFont(family="Verdana", size=20, weight="bold")).pack(side="left", padx=20)

        theme_frame = ctk.CTkFrame(top, fg_color="transparent")
        theme_frame.pack(side="right", padx=20)
        ctk.CTkLabel(theme_frame, text="Theme:", font=ctk.CTkFont(family="Verdana", size=13)).pack(side="left", padx=(0, 8))
        self.theme_var = ctk.StringVar(value="Dark")
        ctk.CTkOptionMenu(theme_frame, values=["Light", "Dark"], variable=self.theme_var,
                          command=self.change_theme, width=110, corner_radius=8,
                          font=ctk.CTkFont(family="Verdana", size=13)).pack(side="left")

        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(side="bottom", fill="x", pady=(0, 10))

        self.status_label = ctk.CTkLabel(bottom_frame, text="Ready", text_color="gray",
                                         font=ctk.CTkFont(family="Verdana", size=12))
        self.status_label.pack(pady=(0, 6))

        ctk.CTkButton(bottom_frame, text="Update Projection", command=self.update_projection,
                      width=280, height=44, corner_radius=10,
                      fg_color="#1565C0", hover_color="#0D47A1",
                      font=ctk.CTkFont(family="Verdana", size=15, weight="bold")).pack()

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        self.main_container.grid_columnconfigure(0, weight=0)
        self.main_container.grid_columnconfigure(1, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # LEFT – Inputs + Dashboard
        self.left_frame = ctk.CTkFrame(self.main_container, width=280, corner_radius=12,
                                       border_width=1, border_color=("#d0d0d0", "#555555"))
        self.left_frame.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        self.left_frame.grid_propagate(False)

        ctk.CTkLabel(self.left_frame, text="Current Inputs",
                     font=ctk.CTkFont(family="Verdana", size=16, weight="bold")).pack(pady=(16, 12))

        form = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        form.pack(padx=14, pady=4)

        ctk.CTkLabel(form, text="Current Balance ($):", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=0, padx=6, pady=8, sticky="e")
        self.balance_entry = ctk.CTkEntry(form, width=130, height=32, corner_radius=8, font=ctk.CTkFont(family="Verdana", size=12))
        self.balance_entry.grid(row=0, column=1, padx=6, pady=8)

        ctk.CTkLabel(form, text="As of Date:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=0, padx=6, pady=8, sticky="e")
        self.asof_entry = DateEntry(form, width=12, background="#2b2b2b", foreground="white",
                                    borderwidth=2, date_pattern="yyyy-mm-dd", font=("Verdana", 11))
        self.asof_entry.grid(row=1, column=1, padx=6, pady=8, sticky="w")

        ctk.CTkLabel(form, text="Safety Buffer ($):", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=2, column=0, padx=6, pady=8, sticky="e")
        self.buffer_entry = ctk.CTkEntry(form, width=130, height=32, corner_radius=8, font=ctk.CTkFont(family="Verdana", size=12))
        self.buffer_entry.grid(row=2, column=1, padx=6, pady=8)

        ctk.CTkButton(self.left_frame, text="Save Inputs", command=self.save_inputs,
                      width=180, height=38, corner_radius=8,
                      font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(pady=(12, 8))

        # ---------- Quick Dashboard ----------
        dash = ctk.CTkFrame(self.left_frame, corner_radius=8,
                            border_width=1, border_color=("#d0d0d0", "#555555"))
        dash.pack(fill="x", padx=10, pady=(4, 12))

        ctk.CTkLabel(dash, text="Quick Overview",
                     font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(pady=(8, 4))

        self.dash_safe_label = ctk.CTkLabel(dash, text="Safe to Spend: —",
                                            font=ctk.CTkFont(family="Verdana", size=12, weight="bold"))
        self.dash_safe_label.pack(anchor="w", padx=10, pady=(0, 4))

        self.dash_bills_frame = ctk.CTkFrame(dash, fg_color="transparent")
        self.dash_bills_frame.pack(fill="x", padx=8, pady=(0, 8))

        # RIGHT – Tabs
        self.right_frame = ctk.CTkFrame(self.main_container, corner_radius=12,
                                        border_width=1, border_color=("#d0d0d0", "#555555"))
        self.right_frame.grid(row=0, column=1, sticky="nsew")

        self.tabview = ctk.CTkTabview(self.right_frame, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.tabview.add("Bills")
        self.tabview.add("Incomes")

        self.tabview._segmented_button.configure(
            font=ctk.CTkFont(family="Verdana", size=15, weight="bold")
        )

        # ---------- BILLS TAB ----------
        bills_tab = self.tabview.tab("Bills")

        add_frame = ctk.CTkFrame(bills_tab, corner_radius=10)
        add_frame.pack(fill="x", pady=4)

        ctk.CTkLabel(add_frame, text="Name:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=0, padx=6, pady=5, sticky="e")
        self.bill_name = ctk.CTkEntry(add_frame, width=150, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_name.grid(row=0, column=1, padx=6, pady=5)

        ctk.CTkLabel(add_frame, text="Amount:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=2, padx=6, pady=5, sticky="e")
        self.bill_amount = ctk.CTkEntry(add_frame, width=100, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_amount.grid(row=0, column=3, padx=6, pady=5)

        ctk.CTkLabel(add_frame, text="Category:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=4, padx=6, pady=5, sticky="e")

        cat_frame = ctk.CTkFrame(add_frame, fg_color="transparent")
        cat_frame.grid(row=0, column=5, padx=6, pady=5, sticky="w")
        self.bill_category = ctk.CTkComboBox(cat_frame, values=self.get_categories(),
                                             width=130, height=30, corner_radius=6,
                                             font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_category.set("Uncategorized")
        self.bill_category.pack(side="left")
        ctk.CTkButton(cat_frame, text="Manage…", width=70, height=26,
                      font=ctk.CTkFont(family="Verdana", size=11),
                      command=self.manage_categories).pack(side="left", padx=(6, 0))

        ctk.CTkLabel(add_frame, text="Frequency:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=0, padx=6, pady=5, sticky="e")
        self.bill_freq = ctk.CTkComboBox(add_frame, values=["Monthly", "Bi-weekly", "Quarterly", "Annual"],
                                         width=120, height=30, corner_radius=6,
                                         command=self.on_frequency_change,
                                         font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_freq.set("Monthly")
        self.bill_freq.grid(row=1, column=1, padx=6, pady=5)

        ctk.CTkLabel(add_frame, text="Next Due Date:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=2, padx=6, pady=5, sticky="e")
        self.bill_anchor = DateEntry(add_frame, width=14, background="#2b2b2b", foreground="white",
                                     borderwidth=2, date_pattern="yyyy-mm-dd", font=("Verdana", 11))
        self.bill_anchor.grid(row=1, column=3, padx=6, pady=5, sticky="w")

        self.bill_month_label = ctk.CTkLabel(add_frame, text="Quarter Cycle:", font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_month_label.grid(row=1, column=4, padx=6, pady=5, sticky="e")
        self.bill_month = ctk.CTkComboBox(add_frame, values=QUARTER_OPTIONS, width=160, height=30,
                                          font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_month.set("Jan / Apr / Jul / Oct")
        self.bill_month.grid(row=1, column=5, padx=6, pady=5)

        btn_frame = ctk.CTkFrame(add_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=6, pady=12)

        self.add_btn = ctk.CTkButton(btn_frame, text="Add Bill", command=self.add_bill, width=120, height=32, corner_radius=8,
                                     fg_color="#2E7D32", hover_color="#1B5E20",
                                     font=ctk.CTkFont(family="Verdana", size=12, weight="bold"))
        self.add_btn.pack(side="left", padx=5)

        self.update_bill_btn = ctk.CTkButton(btn_frame, text="Update Bill", command=self.update_bill, width=120, height=32,
                                             corner_radius=8, state="disabled", font=ctk.CTkFont(family="Verdana", size=12))
        self.update_bill_btn.pack(side="left", padx=5)

        self.cancel_edit_btn = ctk.CTkButton(btn_frame, text="Cancel", command=self.cancel_edit, width=90, height=32,
                                             corner_radius=8, fg_color="gray40", state="disabled",
                                             font=ctk.CTkFont(family="Verdana", size=12))
        self.cancel_edit_btn.pack(side="left", padx=5)

        table_frame = ctk.CTkFrame(bills_tab, corner_radius=10)
        table_frame.pack(fill="both", expand=True, pady=8)

        cols = ("id", "name", "amount", "category", "frequency", "next", "month")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=12)

        headings = {"id": "ID", "name": "Name", "amount": "Amount", "category": "Category",
                    "frequency": "Freq", "next": "Next Due", "month": "Cycle / Month"}
        defaults = {
            "id": 60, "name": 150, "amount": 90, "category": 110,
            "frequency": 90, "next": 110, "month": 120
        }

        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=defaults[c], anchor="center")

        self.load_column_widths(self.tree, "bills_col_widths", defaults)
        self.tree.bind("<ButtonRelease-1>", lambda e: self.save_column_widths(self.tree, "bills_col_widths"))

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        action_frame = ctk.CTkFrame(bills_tab, fg_color="transparent")
        action_frame.pack(fill="x", pady=6, padx=4)

        ctk.CTkLabel(action_frame, text="").pack(side="left", expand=True)

        btn_group = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_group.pack(side="left")

        ctk.CTkButton(btn_group, text="↑ Up", command=self.move_bill_up, width=80, height=30, corner_radius=8).pack(side="left", padx=3)
        ctk.CTkButton(btn_group, text="↓ Down", command=self.move_bill_down, width=80, height=30, corner_radius=8).pack(side="left", padx=3)
        ctk.CTkButton(btn_group, text="Edit", command=self.start_edit_bill, width=90, height=30, corner_radius=8).pack(side="left", padx=3)
        ctk.CTkButton(btn_group, text="Delete", command=self.delete_bill, width=90, height=30, corner_radius=8,
                      fg_color="#C62828", hover_color="#8E0000").pack(side="left", padx=3)

        ctk.CTkLabel(action_frame, text="   ").pack(side="left")

        ctk.CTkLabel(action_frame, text="Search:", font=ctk.CTkFont(family="Verdana", size=12)).pack(side="left", padx=(8, 6))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self.filter_bills)
        ctk.CTkEntry(action_frame, textvariable=self.search_var, width=240, height=32, corner_radius=8,
                     placeholder_text="Filter by name or category...",
                     font=ctk.CTkFont(family="Verdana", size=12)).pack(side="left")

        ctk.CTkLabel(action_frame, text="").pack(side="left", expand=True)

        # ---------- INCOMES TAB ----------
        incomes_tab = self.tabview.tab("Incomes")

        inc_frame = ctk.CTkFrame(incomes_tab, corner_radius=10)
        inc_frame.pack(fill="x", pady=4)

        ctk.CTkLabel(inc_frame, text="Name:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=0, padx=6, pady=5, sticky="e")
        self.inc_name = ctk.CTkEntry(inc_frame, width=150, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_name.grid(row=0, column=1, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Type:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=2, padx=6, pady=5, sticky="e")
        self.inc_type = ctk.CTkComboBox(inc_frame,
                                        values=["Fixed", "Variable", "Hourly", "Passive", "Primary Paycheck"],
                                        width=140, height=30,
                                        command=self.on_income_type_change,
                                        font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_type.set("Fixed")
        self.inc_type.grid(row=0, column=3, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Amount / Rate:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=4, padx=6, pady=5, sticky="e")
        self.inc_amount = ctk.CTkEntry(inc_frame, width=120, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_amount.grid(row=0, column=5, padx=6, pady=5)

        self.inc_hours_label = ctk.CTkLabel(inc_frame, text="Hours:", font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_hours_label.grid(row=1, column=0, padx=6, pady=5, sticky="e")
        self.inc_hours = ctk.CTkEntry(inc_frame, width=150, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_hours.grid(row=1, column=1, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Frequency:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=2, padx=6, pady=5, sticky="e")
        self.inc_freq = ctk.CTkComboBox(inc_frame, values=NORMAL_FREQ_OPTIONS, width=140, height=30,
                                        command=self.on_income_freq_change,
                                        font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_freq.set("Monthly")
        self.inc_freq.grid(row=1, column=3, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Next Date:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=4, padx=6, pady=5, sticky="e")
        self.inc_anchor = DateEntry(inc_frame, width=14, background="#2b2b2b", foreground="white",
                                    borderwidth=2, date_pattern="yyyy-mm-dd", font=("Verdana", 11))
        self.inc_anchor.grid(row=1, column=5, padx=6, pady=5, sticky="w")

        self.inc_interval_label = ctk.CTkLabel(inc_frame, text="Interval (days):", font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_interval_label.grid(row=2, column=0, padx=6, pady=5, sticky="e")
        self.inc_interval = ctk.CTkEntry(inc_frame, width=150, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_interval.grid(row=2, column=1, padx=6, pady=5)

        self.inc_month_label = ctk.CTkLabel(inc_frame, text="Quarter Cycle:", font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_month_label.grid(row=2, column=2, padx=6, pady=5, sticky="e")
        self.inc_month = ctk.CTkComboBox(inc_frame, values=QUARTER_OPTIONS, width=160, height=30,
                                         font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_month.set("Jan / Apr / Jul / Oct")
        self.inc_month.grid(row=2, column=3, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Notes:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=3, column=0, padx=6, pady=5, sticky="e")
        self.inc_notes = ctk.CTkEntry(inc_frame, width=520, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_notes.grid(row=3, column=1, columnspan=5, padx=6, pady=5, sticky="w")

        inc_btn_frame = ctk.CTkFrame(inc_frame, fg_color="transparent")
        inc_btn_frame.grid(row=4, column=0, columnspan=6, pady=10)

        self.add_inc_btn = ctk.CTkButton(inc_btn_frame, text="Add Income", command=self.add_income,
                                         width=120, height=32, corner_radius=8,
                                         fg_color="#2E7D32", hover_color="#1B5E20",
                                         font=ctk.CTkFont(family="Verdana", size=12, weight="bold"))
        self.add_inc_btn.pack(side="left", padx=5)

        self.update_inc_btn = ctk.CTkButton(inc_btn_frame, text="Update Income", command=self.update_income,
                                            width=120, height=32, corner_radius=8, state="disabled",
                                            font=ctk.CTkFont(family="Verdana", size=12))
        self.update_inc_btn.pack(side="left", padx=5)

        self.cancel_inc_btn = ctk.CTkButton(inc_btn_frame, text="Cancel", command=self.cancel_edit_income,
                                            width=90, height=32, corner_radius=8, fg_color="gray40", state="disabled",
                                            font=ctk.CTkFont(family="Verdana", size=12))
        self.cancel_inc_btn.pack(side="left", padx=5)

        inc_table_frame = ctk.CTkFrame(incomes_tab, corner_radius=10)
        inc_table_frame.pack(fill="both", expand=True, pady=8)

        inc_cols = ("id", "name", "type", "amount", "primary", "frequency", "next", "notes")
        self.inc_tree = ttk.Treeview(inc_table_frame, columns=inc_cols, show="headings", height=10)

        defaults_inc = {
            "id": 60, "name": 140, "type": 110, "amount": 90,
            "primary": 80, "frequency": 100, "next": 110, "notes": 160
        }

        for c, h in zip(inc_cols, ["ID", "Name", "Type", "Amount", "Primary", "Frequency", "Next Date", "Notes"]):
            self.inc_tree.heading(c, text=h)
            self.inc_tree.column(c, width=defaults_inc[c], anchor="center")

        self.load_column_widths(self.inc_tree, "incomes_col_widths", defaults_inc)
        self.inc_tree.bind("<ButtonRelease-1>", lambda e: self.save_column_widths(self.inc_tree, "incomes_col_widths"))

        inc_scroll = ttk.Scrollbar(inc_table_frame, orient="vertical", command=self.inc_tree.yview)
        self.inc_tree.configure(yscrollcommand=inc_scroll.set)
        self.inc_tree.pack(side="left", fill="both", expand=True)
        inc_scroll.pack(side="right", fill="y")

        # Incomes action bar (with reorder)
        inc_action_frame = ctk.CTkFrame(incomes_tab, fg_color="transparent")
        inc_action_frame.pack(fill="x", pady=6, padx=4)

        ctk.CTkLabel(inc_action_frame, text="").pack(side="left", expand=True)

        inc_btn_group = ctk.CTkFrame(inc_action_frame, fg_color="transparent")
        inc_btn_group.pack(side="left")

        ctk.CTkButton(inc_btn_group, text="↑ Up", command=self.move_income_up, width=80, height=30, corner_radius=8).pack(side="left", padx=3)
        ctk.CTkButton(inc_btn_group, text="↓ Down", command=self.move_income_down, width=80, height=30, corner_radius=8).pack(side="left", padx=3)
        ctk.CTkButton(inc_btn_group, text="Edit", command=self.start_edit_income, width=90, height=30, corner_radius=8).pack(side="left", padx=3)
        ctk.CTkButton(inc_btn_group, text="Delete", command=self.delete_income, width=90, height=30, corner_radius=8,
                      fg_color="#C62828", hover_color="#8E0000").pack(side="left", padx=3)

        ctk.CTkLabel(inc_action_frame, text="").pack(side="left", expand=True)

    # -------------------- Theme & Helpers --------------------
    def change_theme(self, choice):
        self.apply_theme(choice)
        self.update_dashboard()

    def apply_theme(self, theme):
        style = ttk.Style()
        style.theme_use("clam")

        if theme == "Light":
            ctk.set_appearance_mode("Light")

            # Deeper Cool Gray (much less bright)
            bg_color = "#E8EAED"          # main background
            soft_card = "#F0F2F5"         # large panels (Current Inputs, Bills, Incomes)
            card_color = "#F7F8FA"        # slightly lighter cards
            border_color = "#D1D5DB"
            text_color = "#1F2937"
            heading_bg = "#D1D5DB"

            self.configure(fg_color=bg_color)

            # Treeview
            style.configure("Treeview",
                            background=soft_card,
                            foreground=text_color,
                            fieldbackground=soft_card,
                            font=("Verdana", 11),
                            rowheight=26)
            style.configure("Treeview.Heading",
                            background=heading_bg,
                            foreground=text_color,
                            font=("Verdana", 11, "bold"))
            style.map("Treeview", background=[("selected", "#BFDBFE")])

            # Tabs
            self.tabview._segmented_button.configure(
                fg_color="#D1D5DB",
                selected_color="#3B82F6",
                unselected_color="#9CA3AF",
                text_color="#1F2937",
                selected_hover_color="#2563EB",
                unselected_hover_color="#6B7280",
                font=ctk.CTkFont(family="Verdana", size=15, weight="bold")
            )

            try:
                self.left_frame.configure(fg_color=soft_card, border_color=border_color)
                self.right_frame.configure(fg_color=soft_card, border_color=border_color)
                self.main_container.configure(fg_color=bg_color)
            except Exception:
                pass

        else:
            # ===== DARK THEME =====
            ctk.set_appearance_mode("Dark")
            self.configure(fg_color="#1a1a1a")

            style.configure("Treeview",
                            background="#2b2b2b",
                            foreground="#e0e0e0",
                            fieldbackground="#2b2b2b",
                            font=("Verdana", 11),
                            rowheight=26)
            style.configure("Treeview.Heading",
                            background="#3c3c3c",
                            foreground="#e0e0e0",
                            font=("Verdana", 11, "bold"))

            self.tabview._segmented_button.configure(
                fg_color="#2b2b2b",
                selected_color="#1F6AA5",
                unselected_color="#333333",
                text_color="#ffffff",
                selected_hover_color="#144870",
                unselected_hover_color="#404040",
                font=ctk.CTkFont(family="Verdana", size=15, weight="bold")
            )

            try:
                self.left_frame.configure(fg_color="#2b2b2b", border_color="#555555")
                self.right_frame.configure(fg_color="#2b2b2b", border_color="#555555")
                self.main_container.configure(fg_color="#1a1a1a")
            except Exception:
                pass

    def on_frequency_change(self, choice):
        self.bill_anchor.configure(state="normal")
        if choice == "Quarterly":
            self.bill_month_label.grid()
            self.bill_month.grid()
        else:
            self.bill_month_label.grid_remove()
            self.bill_month.grid_remove()

    def on_income_type_change(self, choice):
        if choice == "Hourly":
            self.inc_hours_label.grid()
            self.inc_hours.grid()
        else:
            self.inc_hours_label.grid_remove()
            self.inc_hours.grid_remove()
            self.inc_hours.delete(0, "end")

        if choice == "Primary Paycheck":
            self.inc_freq.configure(values=SCHEDULE_OPTIONS)
            if self.inc_freq.get() not in SCHEDULE_OPTIONS:
                self.inc_freq.set("Days Interval")
        else:
            self.inc_freq.configure(values=NORMAL_FREQ_OPTIONS)
            if self.inc_freq.get() not in NORMAL_FREQ_OPTIONS:
                self.inc_freq.set("Monthly")

        self.on_income_freq_change(self.inc_freq.get())

    def on_income_freq_change(self, choice):
        is_primary = self.inc_type.get() == "Primary Paycheck"

        if is_primary and choice == "Days Interval":
            self.inc_interval_label.grid()
            self.inc_interval.grid()
        else:
            self.inc_interval_label.grid_remove()
            self.inc_interval.grid_remove()
            self.inc_interval.delete(0, "end")

        if is_primary or choice in ("Bi-weekly", "Monthly", "Quarterly", "Weekly"):
            self.inc_anchor.configure(state="normal")
        else:
            self.inc_anchor.configure(state="disabled")

        if choice == "Quarterly":
            self.inc_month_label.grid()
            self.inc_month.grid()
        else:
            self.inc_month_label.grid_remove()
            self.inc_month.grid_remove()

    def get_quarter_start(self, widget):
        return QUARTER_MAP.get(widget.get(), 1)

    # -------------------- Category helpers --------------------
    def get_categories(self):
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM categories ORDER BY name COLLATE NOCASE")
            rows = [r[0] for r in cur.fetchall()]
        return rows if rows else ["Uncategorized"]

    def ensure_category(self, name):
        name = (name or "").strip()
        if not name:
            return
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
            conn.commit()
        try:
            self.bill_category.configure(values=self.get_categories())
        except Exception:
            pass

    def manage_categories(self):
        win = ctk.CTkToplevel(self)
        win.title("Manage Categories")
        win.geometry("360x420")
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="Categories",
                     font=ctk.CTkFont(family="Verdana", size=15, weight="bold")).pack(pady=(12, 6))

        list_frame = ctk.CTkScrollableFrame(win, width=300, height=240)
        list_frame.pack(pady=4, padx=12, fill="both", expand=True)

        selected = ctk.StringVar()

        def refresh():
            for w in list_frame.winfo_children():
                w.destroy()
            cats = self.get_categories()
            if not cats:
                ctk.CTkLabel(list_frame, text="(no categories yet)").pack(pady=20)
                return
            selected.set(cats[0])
            for c in cats:
                ctk.CTkRadioButton(list_frame, text=c, variable=selected, value=c,
                                   font=ctk.CTkFont(family="Verdana", size=12)).pack(anchor="w", padx=10, pady=2)

        refresh()

        add_row = ctk.CTkFrame(win, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=6)
        new_entry = ctk.CTkEntry(add_row, width=200, placeholder_text="New category…")
        new_entry.pack(side="left", padx=(0, 8))

        def do_add():
            name = new_entry.get().strip()
            if name:
                self.ensure_category(name)
                new_entry.delete(0, "end")
                refresh()

        ctk.CTkButton(add_row, text="Add", width=70, command=do_add).pack(side="left")

        def do_delete():
            name = selected.get()
            if not name:
                return
            if messagebox.askyesno("Delete category",
                                   f"Delete “{name}”?\n(Existing bills keep the old name.)",
                                   parent=win):
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM categories WHERE name=?", (name,))
                    conn.commit()
                refresh()
                self.bill_category.configure(values=self.get_categories())

        ctk.CTkButton(win, text="Delete Selected", fg_color="#C62828", hover_color="#8E0000",
                      command=do_delete).pack(pady=8)

        ctk.CTkButton(win, text="Close", width=100, command=win.destroy).pack(pady=(0, 12))

    # -------------------- Data Methods --------------------
    def save_inputs(self):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM inputs")
                cur.execute("INSERT INTO inputs (current_balance, as_of_date, buffer) VALUES (?,?,?)", (
                    float(self.balance_entry.get() or 0),
                    self.asof_entry.get_date().strftime("%Y-%m-%d"),
                    float(self.buffer_entry.get() or 500)
                ))
                conn.commit()
            self.status_label.configure(text="Inputs saved!", text_color="#9ece6a")
            self.update_dashboard()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def load_inputs(self):
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT current_balance, as_of_date, buffer FROM inputs LIMIT 1")
            row = cur.fetchone()

        today = date.today()
        if row:
            self.balance_entry.delete(0, "end")
            self.balance_entry.insert(0, str(row[0] or 0))
            try:
                self.asof_entry.set_date(datetime.strptime(row[1], "%Y-%m-%d").date())
            except:
                self.asof_entry.set_date(today)
            self.buffer_entry.delete(0, "end")
            self.buffer_entry.insert(0, str(row[2] if row[2] is not None else 500))
        else:
            self.asof_entry.set_date(today)
            self.buffer_entry.insert(0, "500")

    def clear_bill_form(self):
        self.bill_name.delete(0, "end")
        self.bill_amount.delete(0, "end")
        self.bill_category.set("Uncategorized")
        self.bill_freq.set("Monthly")
        self.on_frequency_change("Monthly")
        self.editing_id = None
        self.add_btn.configure(state="normal")
        self.update_bill_btn.configure(state="disabled")
        self.cancel_edit_btn.configure(state="disabled")

    def _validate_amount(self, amount_str, field_name="Amount"):
        try:
            amount = float(amount_str or 0)
        except ValueError:
            messagebox.showerror("Invalid Amount", f"{field_name} must be a number.")
            return None
        if amount < 0:
            if not messagebox.askyesno("Negative Amount",
                                       f"{field_name} is negative (${amount:,.2f}).\n\nContinue anyway?"):
                return None
        return amount

    def _get_valid_date(self, date_widget, field_name="Date"):
        try:
            return date_widget.get_date()
        except Exception:
            messagebox.showerror("Invalid Date", f"Please select a valid {field_name}.")
            return None

    def add_bill(self):
        name = self.bill_name.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Name is required.")
            return
        amount = self._validate_amount(self.bill_amount.get())
        if amount is None:
            return
        try:
            category = self.bill_category.get().strip() or "Uncategorized"
            self.ensure_category(category)
            freq = self.bill_freq.get()
            anchor = self._get_valid_date(self.bill_anchor, "Next Due Date")
            if anchor is None:
                return
            due_day = anchor.day
            month = self.get_quarter_start(self.bill_month) if freq == "Quarterly" else (anchor.month if freq == "Annual" else None)
            anchor_date = anchor.strftime("%Y-%m-%d")

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COALESCE(MAX(sort_order), 0) FROM bills")
                max_order = cur.fetchone()[0]
                cur.execute("""INSERT INTO bills
                    (name, amount, due_day, category, frequency, month, anchor_date, sort_order)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (name, amount, due_day, category, freq, month, anchor_date, max_order + 1))
                conn.commit()

            self.clear_bill_form()
            self.load_bills()
            self.update_dashboard()
            self.status_label.configure(text=f"Added '{name}'", text_color="#9ece6a")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def start_edit_bill(self):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0])["values"]
        self.editing_id = vals[0]

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, amount, category, frequency, month, anchor_date FROM bills WHERE id=?", (vals[0],))
            row = cur.fetchone()

        if not row:
            return

        self.bill_name.delete(0, "end")
        self.bill_name.insert(0, row[0])
        self.bill_amount.delete(0, "end")
        self.bill_amount.insert(0, row[1])
        self.bill_category.set(row[2] or "Uncategorized")
        self.bill_freq.set(row[3])
        self.on_frequency_change(row[3])

        if row[4]:
            self.bill_month.set(REVERSE_QUARTER_MAP.get(row[4], "Jan / Apr / Jul / Oct"))

        if row[5]:
            try:
                self.bill_anchor.set_date(datetime.strptime(row[5], "%Y-%m-%d").date())
            except:
                pass

        self.add_btn.configure(state="disabled")
        self.update_bill_btn.configure(state="normal")
        self.cancel_edit_btn.configure(state="normal")

    def update_bill(self):
        if not self.editing_id:
            return
        name = self.bill_name.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Name is required.")
            return
        amount = self._validate_amount(self.bill_amount.get())
        if amount is None:
            return
        try:
            category = self.bill_category.get().strip() or "Uncategorized"
            self.ensure_category(category)
            freq = self.bill_freq.get()
            anchor = self._get_valid_date(self.bill_anchor, "Next Due Date")
            if anchor is None:
                return
            due_day = anchor.day
            month = self.get_quarter_start(self.bill_month) if freq == "Quarterly" else (anchor.month if freq == "Annual" else None)
            anchor_date = anchor.strftime("%Y-%m-%d")

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""UPDATE bills SET
                    name=?, amount=?, due_day=?, category=?, frequency=?, month=?, anchor_date=?
                    WHERE id=?""",
                    (name, amount, due_day, category, freq, month, anchor_date, self.editing_id))
                conn.commit()

            self.clear_bill_form()
            self.load_bills()
            self.update_dashboard()
            self.status_label.configure(text=f"Updated '{name}'", text_color="#9ece6a")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def cancel_edit(self):
        self.clear_bill_form()

    def load_bills(self):
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT id, name, amount, category, frequency, anchor_date, month
                           FROM bills ORDER BY sort_order, id""")
            self.all_bills = cur.fetchall()
        self.filter_bills()

    def filter_bills(self, *args):
        search = self.search_var.get().lower().strip()
        for i in self.tree.get_children():
            self.tree.delete(i)
        for row in getattr(self, "all_bills", []):
            if search in str(row[1]).lower() or search in str(row[3] or "").lower() or not search:
                r = list(row)
                freq = r[4] or ""
                month_val = r[6]
                if month_val:
                    if freq == "Quarterly":
                        r[6] = REVERSE_QUARTER_MAP.get(month_val, month_val)
                    elif freq == "Annual":
                        r[6] = calendar.month_abbr[month_val] if 1 <= month_val <= 12 else str(month_val)
                    else:
                        r[6] = str(month_val)
                else:
                    r[6] = ""
                self.tree.insert("", "end", values=r)

    def delete_bill(self):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0])["values"]
        if messagebox.askyesno("Confirm", f"Delete '{vals[1]}'?"):
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM bills WHERE id=?", (vals[0],))
                conn.commit()
            self.load_bills()
            self.clear_bill_form()
            self.update_dashboard()

    def move_bill_up(self):
        self._move_bill(-1)

    def move_bill_down(self):
        self._move_bill(1)

    def _move_bill(self, direction):
        sel = self.tree.selection()
        if not sel:
            return
        bill_id = self.tree.item(sel[0])["values"][0]
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, sort_order FROM bills ORDER BY sort_order, id")
            rows = cur.fetchall()
            ids = [r[0] for r in rows]
            orders = [r[1] for r in rows]
            try:
                idx = ids.index(bill_id)
                new_idx = idx + direction
                if 0 <= new_idx < len(ids):
                    cur.execute("UPDATE bills SET sort_order=? WHERE id=?", (orders[new_idx], bill_id))
                    cur.execute("UPDATE bills SET sort_order=? WHERE id=?", (orders[idx], ids[new_idx]))
                    conn.commit()
            except:
                pass
        self.load_bills()

    # ---------- Income methods ----------
    def clear_income_form(self):
        self.inc_name.delete(0, "end")
        self.inc_amount.delete(0, "end")
        self.inc_hours.delete(0, "end")
        self.inc_notes.delete(0, "end")
        self.inc_interval.delete(0, "end")
        self.inc_type.set("Fixed")
        self.inc_freq.set("Monthly")
        self.inc_month.set("Jan / Apr / Jul / Oct")
        self.on_income_type_change("Fixed")
        self.editing_income_id = None
        self.add_inc_btn.configure(state="normal")
        self.update_inc_btn.configure(state="disabled")
        self.cancel_inc_btn.configure(state="disabled")

    def add_income(self):
        name = self.inc_name.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Name is required.")
            return
        amount = self._validate_amount(self.inc_amount.get(), "Amount / Rate")
        if amount is None:
            return
        try:
            hours = float(self.inc_hours.get() or 0) if self.inc_type.get() == "Hourly" else None
            is_primary = 1 if self.inc_type.get() == "Primary Paycheck" else 0
            freq = self.inc_freq.get()
            month = self.get_quarter_start(self.inc_month) if freq == "Quarterly" else None

            if is_primary or freq in ("Bi-weekly", "Monthly", "Quarterly", "Weekly"):
                anchor_dt = self._get_valid_date(self.inc_anchor, "Next Date")
                if anchor_dt is None:
                    return
                anchor = anchor_dt.strftime("%Y-%m-%d")
                due_day = anchor_dt.day
            else:
                anchor = None
                due_day = None

            if is_primary and freq == "Days Interval":
                try:
                    interval = int(self.inc_interval.get() or 14)
                except ValueError:
                    messagebox.showerror("Invalid Interval", "Interval must be a whole number of days.")
                    return
            else:
                interval = None

            with get_db() as conn:
                cur = conn.cursor()
                if is_primary:
                    cur.execute("UPDATE incomes SET is_primary=0")
                cur.execute("SELECT COALESCE(MAX(sort_order), 0) FROM incomes")
                max_order = cur.fetchone()[0]
                cur.execute("""INSERT INTO incomes
                    (name, type, amount, hours, frequency, due_day, month, notes,
                     sort_order, is_primary, anchor_date, interval_days)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (name, self.inc_type.get(), amount, hours, freq, due_day, month,
                     self.inc_notes.get().strip(), max_order + 1, is_primary, anchor, interval))
                conn.commit()

            self.clear_income_form()
            self.load_incomes()
            self.update_dashboard()
            self.status_label.configure(text=f"Added income '{name}'", text_color="#9ece6a")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def start_edit_income(self):
        sel = self.inc_tree.selection()
        if not sel:
            return
        vals = self.inc_tree.item(sel[0])["values"]
        self.editing_income_id = vals[0]

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT name, type, amount, hours, frequency, due_day, month,
                                  notes, is_primary, anchor_date, interval_days
                           FROM incomes WHERE id=?""", (vals[0],))
            row = cur.fetchone()

        if not row:
            return

        self.inc_name.delete(0, "end")
        self.inc_name.insert(0, row[0])
        self.inc_type.set(row[1])
        self.on_income_type_change(row[1])

        self.inc_amount.delete(0, "end")
        self.inc_amount.insert(0, row[2])

        self.inc_hours.delete(0, "end")
        if row[3] is not None:
            self.inc_hours.insert(0, row[3])

        self.inc_freq.set(row[4] or "Monthly")
        self.on_income_freq_change(self.inc_freq.get())

        if row[6] is not None:
            self.inc_month.set(REVERSE_QUARTER_MAP.get(row[6], "Jan / Apr / Jul / Oct"))

        self.inc_notes.delete(0, "end")
        if row[7]:
            self.inc_notes.insert(0, row[7])

        if row[9]:
            try:
                self.inc_anchor.set_date(datetime.strptime(row[9], "%Y-%m-%d").date())
            except:
                pass

        self.inc_interval.delete(0, "end")
        if row[10] is not None:
            self.inc_interval.insert(0, row[10])

        self.add_inc_btn.configure(state="disabled")
        self.update_inc_btn.configure(state="normal")
        self.cancel_inc_btn.configure(state="normal")

    def update_income(self):
        if not self.editing_income_id:
            return
        name = self.inc_name.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Name is required.")
            return
        amount = self._validate_amount(self.inc_amount.get(), "Amount / Rate")
        if amount is None:
            return
        try:
            hours = float(self.inc_hours.get() or 0) if self.inc_type.get() == "Hourly" else None
            is_primary = 1 if self.inc_type.get() == "Primary Paycheck" else 0
            freq = self.inc_freq.get()
            month = self.get_quarter_start(self.inc_month) if freq == "Quarterly" else None

            if is_primary or freq in ("Bi-weekly", "Monthly", "Quarterly", "Weekly"):
                anchor_dt = self._get_valid_date(self.inc_anchor, "Next Date")
                if anchor_dt is None:
                    return
                anchor = anchor_dt.strftime("%Y-%m-%d")
                due_day = anchor_dt.day
            else:
                anchor = None
                due_day = None

            if is_primary and freq == "Days Interval":
                try:
                    interval = int(self.inc_interval.get() or 14)
                except ValueError:
                    messagebox.showerror("Invalid Interval", "Interval must be a whole number of days.")
                    return
            else:
                interval = None

            with get_db() as conn:
                cur = conn.cursor()
                if is_primary:
                    cur.execute("UPDATE incomes SET is_primary=0")
                cur.execute("""UPDATE incomes SET
                    name=?, type=?, amount=?, hours=?, frequency=?, due_day=?, month=?, notes=?,
                    is_primary=?, anchor_date=?, interval_days=?
                    WHERE id=?""",
                    (name, self.inc_type.get(), amount, hours, freq, due_day, month,
                     self.inc_notes.get().strip(), is_primary, anchor, interval, self.editing_income_id))
                conn.commit()

            self.clear_income_form()
            self.load_incomes()
            self.update_dashboard()
            self.status_label.configure(text=f"Updated income '{name}'", text_color="#9ece6a")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def cancel_edit_income(self):
        self.clear_income_form()

    def load_incomes(self):
        for i in self.inc_tree.get_children():
            self.inc_tree.delete(i)
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT id, name, type, amount, is_primary, frequency, anchor_date, notes
                           FROM incomes ORDER BY is_primary DESC, sort_order, id""")
            for row in cur.fetchall():
                primary_str = "★ YES" if row[4] else ""
                next_str = row[6] or ""
                self.inc_tree.insert("", "end", values=(
                    row[0], row[1], row[2], row[3], primary_str, row[5], next_str, row[7] or ""
                ))

    def delete_income(self):
        sel = self.inc_tree.selection()
        if not sel:
            return
        vals = self.inc_tree.item(sel[0])["values"]
        if messagebox.askyesno("Confirm", f"Delete '{vals[1]}'?"):
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM incomes WHERE id=?", (vals[0],))
                conn.commit()
            self.load_incomes()
            self.clear_income_form()
            self.update_dashboard()

    def move_income_up(self):
        self._move_income(-1)

    def move_income_down(self):
        self._move_income(1)

    def _move_income(self, direction):
        sel = self.inc_tree.selection()
        if not sel:
            return
        income_id = self.inc_tree.item(sel[0])["values"][0]
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, sort_order FROM incomes WHERE is_primary=0 ORDER BY sort_order, id")
            rows = cur.fetchall()
            ids = [r[0] for r in rows]
            orders = [r[1] for r in rows]
            try:
                idx = ids.index(income_id)
                new_idx = idx + direction
                if 0 <= new_idx < len(ids):
                    cur.execute("UPDATE incomes SET sort_order=? WHERE id=?", (orders[new_idx], income_id))
                    cur.execute("UPDATE incomes SET sort_order=? WHERE id=?", (orders[idx], ids[new_idx]))
                    conn.commit()
            except ValueError:
                pass
            except:
                pass
        self.load_incomes()

    # -------------------- Dashboard --------------------
    def update_dashboard(self):
        for w in self.dash_bills_frame.winfo_children():
            w.destroy()

        data = self._generate_projection_data(silent=True)
        if not data:
            self.dash_safe_label.configure(text="Safe to Spend: (save inputs first)", text_color="gray")
            return

        safe = data["safe"]
        safe_color = "#2E7D32" if self.theme_var.get() == "Light" else "#9ece6a"
        color = safe_color if safe >= 0 else "#f7768e"
        self.dash_safe_label.configure(text=f"Safe to Spend: ${safe:,.2f}", text_color=color)

        upcoming = []
        for t in data["full_tx"]:
            if t["date"] >= data["as_of"] and t["expense"] > 0 and not t["is_paid"]:
                upcoming.append(t)
                if len(upcoming) >= 3:
                    break

        if not upcoming:
            ctk.CTkLabel(self.dash_bills_frame, text="No upcoming unpaid bills",
                         font=ctk.CTkFont(family="Verdana", size=11), text_color="gray").pack(anchor="w")
        else:
            ctk.CTkLabel(self.dash_bills_frame, text="Next bills:",
                         font=ctk.CTkFont(family="Verdana", size=11, weight="bold")).pack(anchor="w")
            for t in upcoming:
                txt = f"{t['date']}  {t['desc'][:16]}  ${t['expense']:,.0f}"
                ctk.CTkLabel(self.dash_bills_frame, text=txt,
                             font=ctk.CTkFont(family="Verdana", size=11)).pack(anchor="w")

    # -------------------- Projection --------------------
    def update_projection(self):
        try:
            data = self._generate_projection_data()
            if data is None:
                return
            if self.projection_win and self.projection_win.winfo_exists():
                self._refresh_projection_window(data)
            else:
                self._create_projection_window(data)
        except Exception as e:
            messagebox.showerror("Projection Error", str(e))

    def _generate_projection_data(self, silent=False):
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT current_balance, as_of_date, buffer FROM inputs LIMIT 1")
            inp = cur.fetchone()
            if not inp:
                if not silent:
                    messagebox.showwarning("Missing", "Save Inputs first.")
                return None

            current_balance = float(inp[0] or 0)
            as_of = datetime.strptime(inp[1], "%Y-%m-%d").date()
            buffer = float(inp[2] or 500)

            cur.execute("""SELECT name, amount, frequency, anchor_date, interval_days
                           FROM incomes WHERE is_primary=1 LIMIT 1""")
            primary = cur.fetchone()

            cur.execute("""SELECT name, type, amount, hours, frequency, due_day, month, is_primary, anchor_date
                           FROM incomes ORDER BY sort_order, id""")
            income_rows = cur.fetchall()

            cur.execute("""SELECT name, amount, due_day, category, frequency, month, anchor_date
                           FROM bills ORDER BY sort_order, id""")
            bill_rows = cur.fetchall()

            cur.execute("SELECT date, description FROM paid_transactions")
            previously_paid = {f"{d}|{desc}" for d, desc in cur.fetchall()}

        month_start = as_of.replace(day=1)
        lookback = min(as_of - timedelta(days=10), month_start - timedelta(days=40))
        end_date = as_of + relativedelta(months=12)

        all_paychecks = []
        pay_amt = 0.0
        next_pay = as_of + timedelta(days=30)

        if primary:
            _, pay_amt, schedule, anchor_str, interval = primary
            pay_amt = float(pay_amt or 0)
            interval = int(interval or 14)
            try:
                next_pay = datetime.strptime(anchor_str, "%Y-%m-%d").date()
            except:
                next_pay = as_of

            if schedule == "Days Interval":
                p = next_pay - timedelta(days=interval * 3)
                while p <= end_date:
                    all_paychecks.append(p)
                    p += timedelta(days=interval)
            else:
                if "14th & 28th" in (schedule or ""):
                    target_days, use_eom = [14, 28], False
                elif "1st & 15th" in (schedule or ""):
                    target_days, use_eom = [1, 15], False
                else:
                    target_days, use_eom = [15], True

                curr = (lookback - relativedelta(months=1)).replace(day=1)
                while curr <= end_date + relativedelta(months=1):
                    y, m = curr.year, curr.month
                    last = calendar.monthrange(y, m)[1]
                    for td in target_days:
                        due = date(y, m, min(td, last))
                        if lookback <= due <= end_date:
                            all_paychecks.append(due)
                    if use_eom:
                        due = date(y, m, last)
                        if lookback <= due <= end_date:
                            all_paychecks.append(due)
                    curr += relativedelta(months=1)
                all_paychecks = sorted(set(all_paychecks))

            future = [d for d in all_paychecks if d >= as_of]
            if future:
                next_pay = min(future)

        tx = []

        # Primary paychecks – respect paid status
        for pdate in all_paychecks:
            if lookback <= pdate <= end_date:
                key = f"{pdate}|Paycheck"
                paid = key in previously_paid
                tx.append({
                    "date": pdate,
                    "desc": "Paycheck",
                    "category": "Income",
                    "income": pay_amt,
                    "expense": 0.0,
                    "is_paid": paid
                })

        def make_due(year, month, day):
            last = calendar.monthrange(year, month)[1]
            return date(year, month, min(day, last))

        # Other incomes
        for name, typ, amount, hours, freq, due_day, month, is_prim, anchor_date in income_rows:
            if is_prim:
                continue

            name = str(name).strip()
            amount = float(amount or 0)
            hours = float(hours or 0)
            final_amount = amount * hours if typ == "Hourly" else amount
            if final_amount == 0:
                continue

            if not anchor_date:
                continue

            try:
                anchor = datetime.strptime(anchor_date, "%Y-%m-%d").date()
            except:
                continue

            day = anchor.day
            start_month = int(month) if month else 1
            dates = []

            if freq == "Bi-weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=14)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        dates.append(d)
                    d += timedelta(days=14)

            elif freq == "Weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=7)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        dates.append(d)
                    d += timedelta(days=7)

            elif freq == "Monthly":
                d = anchor
                for _ in range(3):
                    d = d - relativedelta(months=1)
                while d <= end_date:
                    due = make_due(d.year, d.month, day)
                    if lookback <= due <= end_date:
                        dates.append(due)
                    d = d + relativedelta(months=1)

            elif freq == "Quarterly":
                start_m = start_month - 1
                d = anchor
                for _ in range(4):
                    d = d - relativedelta(months=3)
                while d <= end_date + relativedelta(months=3):
                    due = make_due(d.year, d.month, day)
                    if (due.month - 1 - start_m) % 3 == 0 and lookback <= due <= end_date:
                        dates.append(due)
                    d = d + relativedelta(months=1)

            for d in dates:
                key = f"{d}|{name}"
                paid = key in previously_paid
                tx.append({
                    "date": d,
                    "desc": name,
                    "category": "Income",
                    "income": final_amount,
                    "expense": 0.0,
                    "is_paid": paid
                })

        # Bills
        for name, amount, due_day, category, frequency, month, anchor_date in bill_rows:
            bill_name = str(name).strip()
            amt = float(amount or 0)
            cat = category or "Uncategorized"
            freq = (frequency or "Monthly").lower()
            day = int(due_day or 1)
            bill_month = int(month) if month else None

            if not anchor_date:
                continue

            try:
                anchor = datetime.strptime(anchor_date, "%Y-%m-%d").date()
            except:
                continue

            dates = []

            if freq == "bi-weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=14)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        dates.append(d)
                    d += timedelta(days=14)

            elif freq == "monthly":
                d = anchor
                for _ in range(3):
                    d = d - relativedelta(months=1)
                while d <= end_date:
                    due = make_due(d.year, d.month, day)
                    if lookback <= due <= end_date:
                        dates.append(due)
                    d = d + relativedelta(months=1)

            elif freq == "quarterly":
                start_m = (bill_month - 1) if bill_month else 0
                d = anchor
                for _ in range(4):
                    d = d - relativedelta(months=3)
                while d <= end_date + relativedelta(months=3):
                    due = make_due(d.year, d.month, day)
                    if (due.month - 1 - start_m) % 3 == 0 and lookback <= due <= end_date:
                        dates.append(due)
                    d = d + relativedelta(months=1)

            elif freq == "annual":
                d = anchor
                for _ in range(2):
                    d = d - relativedelta(years=1)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        dates.append(d)
                    d = d + relativedelta(years=1)

            for d in dates:
                key = f"{d}|{bill_name}"
                paid = key in previously_paid
                tx.append({
                    "date": d,
                    "desc": bill_name,
                    "category": cat,
                    "income": 0.0,
                    "expense": amt,
                    "is_paid": paid
                })

        tx.sort(key=lambda x: x["date"])

        full_tx = tx[:]
        tx = [t for t in full_tx if t["date"] >= month_start]

        eom = (as_of + relativedelta(months=1)).replace(day=1)

        def unpaid_expense(t):
            return t["expense"] if not t["is_paid"] else 0.0

        def unpaid_income(t):
            return t["income"] if not t["is_paid"] else 0.0

        bills_next = sum(unpaid_expense(t) for t in full_tx if as_of <= t["date"] < next_pay)
        bills_eom  = sum(unpaid_expense(t) for t in full_tx if as_of <= t["date"] <= eom)

        other_inc_next = sum(unpaid_income(t) for t in full_tx
                             if as_of <= t["date"] < next_pay
                             and t["category"] == "Income" and t["desc"] != "Paycheck")
        other_inc_eom  = sum(unpaid_income(t) for t in full_tx
                             if as_of <= t["date"] <= eom
                             and t["category"] == "Income" and t["desc"] != "Paycheck")

        primary_eom = sum(unpaid_income(t) for t in full_tx
                          if as_of <= t["date"] <= eom and t["desc"] == "Paycheck")

        if self.safe_period == "eom":
            bills_in_window   = bills_eom
            income_in_window  = primary_eom + (other_inc_eom if self.safe_inclusive else 0.0)
            period_label      = f"Until 1st of next month (through {eom})"
            primary_in_window = primary_eom
            bal_after = current_balance - bills_eom + primary_eom
            bal_label = "Balance after 1st of next month"
        else:
            bills_in_window   = bills_next
            income_in_window  = other_inc_next if self.safe_inclusive else 0.0
            period_label      = f"Next Pay ({next_pay})"
            primary_in_window = 0.0
            bal_after = current_balance - bills_next + pay_amt
            bal_label = "Balance after next pay"

        safe = current_balance - bills_in_window + income_in_window - buffer

        # 30-day pie
        thirty = as_of + timedelta(days=30)
        cat_totals = {}
        total_inc = total_exp = 0.0
        for t in full_tx:
            if as_of <= t["date"] <= thirty:
                total_inc += unpaid_income(t)
                exp = unpaid_expense(t)
                if exp > 0:
                    total_exp += exp
                    cat_totals[t["category"]] = cat_totals.get(t["category"], 0) + exp
        if total_inc - total_exp > 0:
            cat_totals["Savings"] = total_inc - total_exp

        # 12 months for dropdown
        month_options = []
        for i in range(12):
            m = (as_of.replace(day=1) + relativedelta(months=i))
            label = m.strftime("%B %Y")
            month_options.append((label, m.year, m.month))

        return {
            "tx": tx,
            "full_tx": full_tx,
            "start_bal": current_balance,
            "as_of": as_of,
            "safe": safe,
            "next_pay": next_pay,
            "pay_amt": pay_amt,
            "bills_before": bills_in_window,
            "bal_after": bal_after,
            "bal_label": bal_label,
            "buffer": buffer,
            "cat_totals": cat_totals,
            "has_primary": primary is not None,
            "period_label": period_label,
            "income_in_window": income_in_window,
            "primary_in_window": primary_in_window,
            "safe_period": self.safe_period,
            "safe_inclusive": self.safe_inclusive,
            "month_options": month_options,
        }

    def _create_projection_window(self, data):
        win = ctk.CTkToplevel(self)
        win.title(f"Budget Projection — {CURRENT_DB}")
        x = self.winfo_x() + 80
        y = self.winfo_y() + 80
        win.geometry(f"1280x860+{x}+{y}")
        win.protocol("WM_DELETE_WINDOW", self._on_projection_close)

        # Actions menu (Mark past / Clear paid)
        menubar = Menu(win)
        win.configure(menu=menubar)
        actions = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Actions", menu=actions)
        actions.add_command(label="Mark all past as paid", command=self._mark_past_paid)
        actions.add_command(label="Clear all paid flags", command=self._clear_all_paid)

        win.after(50, lambda: (win.lift(), win.focus_force()))
        self.projection_win = win
        self._build_projection_content(win, data)

    def _refresh_projection_window(self, data):
        if not self.projection_win or not self.projection_win.winfo_exists():
            self._create_projection_window(data)
            return
        for w in self.projection_win.winfo_children():
            w.destroy()
        self._build_projection_content(self.projection_win, data)
        self.projection_win.after(50, lambda: (self.projection_win.lift(), self.projection_win.focus_force()))

    def _on_projection_close(self):
        if self.projection_win:
            try:
                self.projection_win.destroy()
            except:
                pass
        self.projection_win = None

    def _on_safe_period_change(self, choice):
        self.safe_period = "eom" if choice == "Until End of Month" else "next_pay"
        self.save_safe_settings()
        self.update_projection()
        self.update_dashboard()

    def _on_safe_mode_change(self, choice):
        self.safe_inclusive = (choice == "Inclusive")
        self.save_safe_settings()
        self.update_projection()
        self.update_dashboard()

    def _mark_past_paid(self):
        data = self._generate_projection_data(silent=True)
        if not data:
            return
        as_of = data["as_of"]
        count = 0
        with get_db() as conn:
            cur = conn.cursor()
            for t in data["full_tx"]:
                if t["date"] < as_of and not t["is_paid"]:
                    cur.execute("INSERT OR IGNORE INTO paid_transactions (date, description) VALUES (?,?)",
                                (str(t["date"]), t["desc"]))
                    count += 1
            conn.commit()
        self.status_label.configure(text=f"Marked {count} past items as paid", text_color="#9ece6a")
        if self.projection_win and self.projection_win.winfo_exists():
            self.update_projection()
        self.update_dashboard()

    def _clear_all_paid(self):
        if not messagebox.askyesno("Clear all paid flags",
                                   "This will remove every paid mark.\n\nContinue?"):
            return
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM paid_transactions")
            conn.commit()
        self.status_label.configure(text="All paid flags cleared", text_color="#9ece6a")
        if self.projection_win and self.projection_win.winfo_exists():
            self.update_projection()
        self.update_dashboard()

    def _build_projection_content(self, win, data):
        tx = data["tx"]
        full_tx = data["full_tx"]
        start_bal = data["start_bal"]
        as_of = data["as_of"]
        safe = data["safe"]
        next_pay = data["next_pay"]
        pay_amt = data["pay_amt"]
        bills_before = data["bills_before"]
        bal_after = data["bal_after"]
        bal_label = data["bal_label"]
        buffer = data["buffer"]
        cat_totals = data["cat_totals"]
        has_primary = data.get("has_primary", False)
        month_options = data["month_options"]

        sum_frame = ctk.CTkFrame(win, corner_radius=10)
        sum_frame.pack(fill="x", padx=14, pady=(8, 6))

        # Left: SAFE TO SPEND + warning underneath
        left = ctk.CTkFrame(sum_frame, fg_color="transparent", width=210)
        left.grid(row=0, column=0, padx=16, pady=8, sticky="nw")
        left.grid_propagate(False)

        ctk.CTkLabel(left, text="SAFE TO SPEND",
                    font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(anchor="w")
        
        # Theme-aware readable green
        safe_color = "#2E7D32" if self.theme_var.get() == "Light" else "#9ece6a"
        color = safe_color if safe >= 0 else "#f7768e"
        
        ctk.CTkLabel(left, text=f"${safe:,.2f}",
                    font=ctk.CTkFont(family="Verdana", size=26, weight="bold"),
                    text_color=color).pack(anchor="w", pady=(2, 0))
        
        if safe < 0:
            ctk.CTkLabel(left, text=f"⚠ Buffer short (${buffer})",
                        text_color="#f7768e",
                        font=ctk.CTkFont(family="Verdana", size=12, weight="bold")).pack(anchor="w", pady=(4, 0))

        # Middle: Period + Mode
        ctrl = ctk.CTkFrame(sum_frame, fg_color="transparent")
        ctrl.grid(row=0, column=1, padx=20, pady=8, sticky="nw")

        ctk.CTkLabel(ctrl, text="Period:", font=ctk.CTkFont(family="Verdana", size=12)).grid(
            row=0, column=0, sticky="e", padx=(0, 8), pady=3)
        period_var = ctk.StringVar(
            value="Until Next Pay" if data["safe_period"] == "next_pay" else "Until End of Month")
        ctk.CTkOptionMenu(ctrl, values=["Until Next Pay", "Until End of Month"],
                        variable=period_var, width=170,
                        command=self._on_safe_period_change,
                        font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=1, pady=3)

        ctk.CTkLabel(ctrl, text="Mode:", font=ctk.CTkFont(family="Verdana", size=12)).grid(
            row=1, column=0, sticky="e", padx=(0, 8), pady=3)
        mode_var = ctk.StringVar(value="Inclusive" if data["safe_inclusive"] else "Strict")
        ctk.CTkOptionMenu(ctrl, values=["Strict", "Inclusive"],
                        variable=mode_var, width=170,
                        command=self._on_safe_mode_change,
                        font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=1, pady=3)

        # Right: Info block
        info = ctk.CTkFrame(sum_frame, fg_color="transparent", width=340)
        info.grid(row=0, column=2, padx=16, pady=8, sticky="nw")

        if has_primary:
            ctk.CTkLabel(info, text=f"Window: {data['period_label']}",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")
            ctk.CTkLabel(info, text=f"Bills in window: ${bills_before:,.2f}",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")

            if data["safe_period"] == "eom":
                if data["safe_inclusive"]:
                    income_text = f"+ Incomes (incl. primary): ${data['income_in_window']:,.2f}"
                else:
                    income_text = f"+ Primary paycheck(s): ${data.get('primary_in_window', 0):,.2f}"
            else:
                income_text = f"+ Other income: ${data['income_in_window']:,.2f}" if data["safe_inclusive"] else " "
            ctk.CTkLabel(info, text=income_text,
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")

            ctk.CTkLabel(info, text=f"{bal_label}: ${bal_after:,.2f}",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")
        else:
            ctk.CTkLabel(info, text="No Primary Paycheck set", text_color="#f7768e",
                        font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(anchor="w")

        content = ctk.CTkFrame(win, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=6)

        table_frame = ctk.CTkFrame(content, corner_radius=10)
        table_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        cols = ("date", "desc", "category", "income", "expense", "balance", "paid")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=27)
        for c, h in zip(cols, ["Date", "Description", "Category", "Income", "Expense", "Running Bal", "Paid?"]):
            tree.heading(c, text=h)
            tree.column(c, width=110 if c != "desc" else 180, anchor="center")

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # Paid row styling (grey)
        if self.theme_var.get() == "Light":
            tree.tag_configure("paid", background="#e0e0e0", foreground="#666666")
        else:
            tree.tag_configure("paid", background="#3a3a3a", foreground="#aaaaaa")

        past_rows   = [t for t in tx if t["date"] < as_of]
        future_rows = [t for t in tx if t["date"] >= as_of]

        for t in past_rows:
            paid_symbol = "☑" if t["is_paid"] else "☐"
            month_idx = t["date"].month - 1
            tags = [f"month{month_idx}", f"{t['date']}|{t['desc']}"]
            if t["is_paid"]:
                tags.append("paid")
            tree.insert("", "end", values=(
                t["date"], t["desc"], t["category"],
                f"{t['income']:,.2f}" if t["income"] else "",
                f"{t['expense']:,.2f}" if t["expense"] else "",
                "—",
                paid_symbol
            ), tags=tuple(tags))

        tree.insert("", "end", values=(as_of, "Starting Balance", "", "", "", f"{start_bal:,.2f}", ""),
                    tags=("startbal",))

        balance = start_bal
        for t in future_rows:
            inc = t["income"] if not t["is_paid"] else 0.0
            exp = t["expense"] if not t["is_paid"] else 0.0
            balance += inc - exp
            paid_symbol = "☑" if t["is_paid"] else "☐"
            month_idx = t["date"].month - 1
            tags = [f"month{month_idx}", f"{t['date']}|{t['desc']}"]
            if t["is_paid"]:
                tags.append("paid")
            tree.insert("", "end", values=(
                t["date"], t["desc"], t["category"],
                f"{t['income']:,.2f}" if t["income"] else "",
                f"{t['expense']:,.2f}" if t["expense"] else "",
                f"{balance:,.2f}", paid_symbol
            ), tags=tuple(tags))

        colors = MONTH_COLORS_LIGHT if self.theme_var.get() == "Light" else MONTH_COLORS_DARK
        text_color = "#000000" if self.theme_var.get() == "Light" else "#e0e0e0"
        for i, color in enumerate(colors):
            tree.tag_configure(f"month{i}", background=color, foreground=text_color)

        def toggle_paid(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            tags = tree.item(item, "tags")
            if len(tags) < 2:
                return
            date_str, desc = tags[1].split("|", 1)
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM paid_transactions WHERE date=? AND description=?", (date_str, desc))
                if cur.fetchone():
                    cur.execute("DELETE FROM paid_transactions WHERE date=? AND description=?", (date_str, desc))
                else:
                    cur.execute("INSERT OR IGNORE INTO paid_transactions (date, description) VALUES (?,?)", (date_str, desc))
                conn.commit()
            new_data = self._generate_projection_data()
            if new_data:
                self._refresh_projection_window(new_data)
            self.update_dashboard()

        tree.bind("<Double-1>", toggle_paid)

        # Clickable month colours → jump This Month dropdown
        def on_row_click(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            tags = tree.item(item, "tags")
            if not tags or not str(tags[0]).startswith("month"):
                return
            try:
                m_idx = int(str(tags[0])[5:])
                for label, y, m in month_options:
                    if m == m_idx + 1:
                        self.month_var.set(label)
                        self._update_month_panel(label)
                        break
            except Exception:
                pass

        tree.bind("<ButtonRelease-1>", on_row_click)

        # RIGHT SIDE (Chart + This Month)
        chart_frame = ctk.CTkFrame(content, width=400, corner_radius=10)
        chart_frame.pack(side="right", fill="y")
        chart_frame.pack_propagate(False)

        ctk.CTkLabel(chart_frame, text="Next 30 Days – Expenses",
                    font=ctk.CTkFont(family="Verdana", size=14, weight="bold")).pack(pady=(12, 6))

        if cat_totals:
            n = len(cat_totals)
            # Legend ~20% bigger
            if n > 8:
                fontsize, ncol, bottom, fig_h = 9.0, 3, 0.34, 4.25
            elif n > 5:
                fontsize, ncol, bottom, fig_h = 10, 2, 0.29, 4.15
            else:
                fontsize, ncol, bottom, fig_h = 10.6, 2, 0.27, 4.05

            is_dark = self.theme_var.get() == "Dark"

            fig, ax = plt.subplots(figsize=(3.95, fig_h), dpi=100)

            if is_dark:
                fig.patch.set_facecolor("#2b2b2b")
                ax.set_facecolor("#2b2b2b")
                legend_color = "#e0e0e0"
            else:
                fig.patch.set_facecolor("white")
                ax.set_facecolor("white")
                legend_color = "black"

            wedges, texts, autotexts = ax.pie(
                list(cat_totals.values()),
                labels=None,
                autopct="%1.1f%%",
                startangle=90,
                colors=plt.cm.Set3.colors[:n],
                pctdistance=0.75
            )

            for autotext in autotexts:
                autotext.set_fontsize(9)
                autotext.set_color("#333333" if is_dark else "black")

            ax.axis("equal")

            legend_labels = [f"{cat}  ${val:,.0f}" for cat, val in cat_totals.items()]
            legend = ax.legend(
                wedges, legend_labels,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.05),
                ncol=ncol,
                frameon=False,
                fontsize=fontsize,
                handlelength=1.1,
                handletextpad=0.4,
                columnspacing=1.0
            )

            for text in legend.get_texts():
                text.set_color(legend_color)

            fig.tight_layout()
            fig.subplots_adjust(bottom=bottom)

            canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(pady=(0, 4), padx=8, expand=False)
            plt.close(fig)
        else:
            ctk.CTkLabel(chart_frame, text="No expenses in next 30 days",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(pady=40)
                                                
        # THIS MONTH panel (tight spacing)
        this_month = ctk.CTkFrame(chart_frame, corner_radius=8,
                                  border_width=1, border_color=("#d0d0d0", "#555555"))
        this_month.pack(fill="x", padx=10, pady=(6, 10))

        ctk.CTkLabel(this_month, text="This Month",
                     font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(pady=(8, 2))

        this_month_labels = {}
        self._month_panel_data = {
            "full_tx": full_tx,
            "labels": this_month_labels,
            "options": month_options
        }

        month_labels = [opt[0] for opt in month_options]
        self.month_var = ctk.StringVar(value=month_labels[0])

        def on_month_change(choice):
            self._update_month_panel(choice)

        month_menu = ctk.CTkOptionMenu(
            this_month,
            values=month_labels,
            variable=self.month_var,
            width=200,
            command=on_month_change
        )
        month_menu.pack(pady=(0, 6))

        def make_row(parent, title, key, color=None):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(family="Verdana", size=12)).pack(side="left")
            lbl = ctk.CTkLabel(frame, text="$0.00",
                               font=ctk.CTkFont(family="Verdana", size=12, weight="bold"),
                               text_color=color)
            lbl.pack(side="right")
            this_month_labels[key] = lbl

        make_row(this_month, "Income:", "income", "#2E7D32")
        make_row(this_month, "Expenses:", "expense", "#C62828")
        make_row(this_month, "Net:", "net")
        make_row(this_month, "Still unpaid:", "unpaid", "#E65100")

        ctk.CTkLabel(this_month, text="", height=6).pack()

        self._update_month_panel(month_labels[0])

    def _update_month_panel(self, choice):
        if not hasattr(self, "_month_panel_data"):
            return

        data = self._month_panel_data
        full_tx = data["full_tx"]
        labels = data["labels"]
        options = data["options"]

        year = month = None
        for label, y, m in options:
            if label == choice:
                year, month = y, m
                break
        if year is None:
            return

        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        income = sum(t["income"] for t in full_tx if month_start <= t["date"] <= month_end)
        expense = sum(t["expense"] for t in full_tx if month_start <= t["date"] <= month_end and t["expense"] > 0)
        unpaid = sum(t["expense"] for t in full_tx
                     if month_start <= t["date"] <= month_end and t["expense"] > 0 and not t["is_paid"])
        net = income - expense

        # Theme-aware colours
        income_color = "#2E7D32" if self.theme_var.get() == "Light" else "#9ece6a"
        net_color = income_color if net >= 0 else "#C62828"

        labels["income"].configure(text=f"${income:,.2f}", text_color=income_color)
        labels["expense"].configure(text=f"${expense:,.2f}")
        labels["unpaid"].configure(text=f"${unpaid:,.2f}")
        labels["net"].configure(text=f"${net:,.2f}", text_color=net_color)

        safe_color = "#2E7D32" if self.theme_var.get() == "Light" else "#9ece6a"
        net_color = safe_color if net >= 0 else "#C62828"
        labels["net"].configure(text=f"${net:,.2f}", text_color=net_color)

# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    last = load_last_budget()
    if last:
        CURRENT_DB = last
        app = BudgetApp()
        app.mainloop()
    else:
        launcher = BudgetLauncher()
        launcher.mainloop()
