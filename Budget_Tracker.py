__version__ = "0.91"

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
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import atexit

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
    except Exception:
        pass

def load_last_budget():
    try:
        with open(get_last_budget_file(), "r") as f:
            name = f.read().strip()
            if name and os.path.exists(get_db_path(name)):
                return name
    except Exception:
        pass
    return None

def get_lock_path(db_name):
    return os.path.join(get_base_path(), f".{db_name}.lock")

def acquire_lock(db_name):
    lock_path = get_lock_path(db_name)
    try:
        if os.path.exists(lock_path):
            return False
        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False

def release_lock(db_name):
    lock_path = get_lock_path(db_name)
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass

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
                sort_order INTEGER DEFAULT 0,
                notes TEXT
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
                anchor_date TEXT
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
            ("bills", "notes", "TEXT"),
            ("incomes", "is_primary", "INTEGER DEFAULT 0"),
            ("incomes", "anchor_date", "TEXT"),
            ("incomes", "sort_order", "INTEGER DEFAULT 0"),
        ]:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except Exception:
                pass

        try:
            cur.execute("UPDATE incomes SET type='Fixed' WHERE type='Primary Paycheck'")
            conn.commit()
        except Exception:
            pass

        conn.commit()

# ------------------------------------------------------------------
# Tooltips
# ------------------------------------------------------------------
class TreeviewTooltip:
    def __init__(self, tree, get_text_func, delay=450):
        self.tree = tree
        self.get_text = get_text_func
        self.delay = delay
        self.tipwindow = None
        self.after_id = None
        self.tree.bind("<Motion>", self._schedule)
        self.tree.bind("<Leave>", self._hide)

    def _schedule(self, event):
        self._hide()
        item = self.tree.identify_row(event.y)
        if not item:
            return
        text = self.get_text(item)
        if not text or not str(text).strip():
            return
        self.after_id = self.tree.after(self.delay, lambda: self._show(event, text))

    def _show(self, event, text):
        if self.tipwindow:
            return
        x = self.tree.winfo_pointerx() + 16
        y = self.tree.winfo_pointery() + 12
        self.tipwindow = tw = ctk.CTkToplevel(self.tree)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2b2b2b" if is_dark else "#F0F2F5"
        fg = "#e0e0e0" if is_dark else "#1F2937"
        border_col = "#3B82F6"

        border = ctk.CTkFrame(tw, fg_color=border_col, corner_radius=8)
        border.pack()
        inner = ctk.CTkFrame(border, fg_color=bg, corner_radius=6)
        inner.pack(padx=3, pady=3)

        lbl = ctk.CTkLabel(
            inner, text=str(text), fg_color="transparent", text_color=fg,
            font=ctk.CTkFont(family="Verdana", size=12),
            wraplength=340, justify="left", padx=10, pady=7
        )
        lbl.pack()
        tw.bind("<Leave>", lambda e: self._hide())

    def _hide(self, event=None):
        if self.after_id:
            try:
                self.tree.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.tipwindow:
            try:
                self.tipwindow.destroy()
            except Exception:
                pass
            self.tipwindow = None


class WidgetTooltip:
    def __init__(self, widget, text, delay=400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tipwindow = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, event=None):
        self._hide()
        self.after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self.tipwindow:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tipwindow = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)

        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2b2b2b" if is_dark else "#F0F2F5"
        fg = "#e0e0e0" if is_dark else "#1F2937"
        border_col = "#3B82F6"

        border = ctk.CTkFrame(tw, fg_color=border_col, corner_radius=8)
        border.pack()

        inner = ctk.CTkFrame(border, fg_color=bg, corner_radius=6)
        inner.pack(padx=2.5, pady=2.5)

        lbl = ctk.CTkLabel(
            inner,
            text=self.text,
            fg_color="transparent",
            text_color=fg,
            font=ctk.CTkFont(family="Verdana", size=12),
            wraplength=280,
            justify="left",
            padx=10,
            pady=7
        )
        lbl.pack()

    def _hide(self, event=None):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.tipwindow:
            try:
                self.tipwindow.destroy()
            except Exception:
                pass
            self.tipwindow = None

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

        if not acquire_lock(name):
            messagebox.showerror(
                "Budget already open",
                f"The budget file “{name}” is already open in another window.\n\n"
                "Please close the other instance first."
            )
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

        if not acquire_lock(name):
            messagebox.showerror(
                "Budget already open",
                f"The budget file “{name}” is already open in another window.\n\n"
                "Please close the other instance first."
            )
            return

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
    "#d0e2f3", "#c8e6c9", "#fff9c4", "#e1bee7",
    "#ffe0b2", "#b3e5fc", "#ffccbc", "#c5cae9",
    "#fff9c4", "#f8bbd0", "#b2dfdb", "#dcedc8"
]

MONTH_COLORS_DARK = [
    "#1E3A5F", "#123D2B", "#1E2A4A", "#1b4332",
    "#1E3A5F", "#123D2B", "#1E2A4A", "#1b4332",
    "#1E3A5F", "#123D2B", "#1E2A4A", "#1b4332"
]

NORMAL_FREQ_OPTIONS = ["Weekly", "Bi-weekly", "Monthly", "Quarterly", "One-time"]
EXPENSE_FREQ_OPTIONS = ["Weekly", "Bi-weekly", "Monthly", "Quarterly", "Annual", "One-time"]

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

        ctk.set_default_color_theme("blue")

        self.projection_win = None
        self.editing_id = None
        self.editing_income_id = None
        self.hide_paid = False
        self.form_is_main = False
        self.inc_notes = {}
        self.bill_notes = {}
        self.safe_end_date = None
        self._proj_canvas = None
        self._proj_fig = None
        self._highlighted_category = None
        self.drag_item = None
        self.drag_tree = None
        self._treemap_canvas = None
        self._treemap_fig = None
        self._search_after_id = None

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        atexit.register(lambda: release_lock(CURRENT_DB))

        self.bind_all("<Control-s>", lambda e: self.save_inputs())
        self.bind_all("<Control-S>", lambda e: self.save_inputs())

        menubar = Menu(self)
        self.configure(menu=menubar)
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Switch Budget…", command=self.switch_budget)
        file_menu.add_command(label="New Budget…", command=self.new_budget)
        file_menu.add_separator()
        file_menu.add_command(label="Tips & Shortcuts…", command=self.show_shortcuts)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)

        init_database()

        # Load last used theme
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key='theme'")
            row = cur.fetchone()
        self.last_theme = row[0] if row and row[0] in ("Light", "Dark") else "Dark"

        ctk.set_appearance_mode(self.last_theme)

        self.create_widgets()
        self.apply_theme(self.last_theme)
        self._style_scrollbars()
        self._style_dateentries()
        self.load_inputs()
        self.load_bills()
        self.load_incomes()
        self.on_frequency_change("Monthly")
        self.on_income_type_change("Fixed")
        self.update_dashboard()

    def _style_dateentries(self):
        is_dark = self.theme_var.get() == "Dark"
        if is_dark:
            bg = "#1f1f1f"
            fg = "white"
            headersbg = "#3c3c3c"
            headersfg = "white"
        else:
            bg = "#3b8ed0"
            fg = "#181818"
            headersbg = "#9cdcfe"
            headersfg = "#181818"

        for entry in (self.asof_entry, self.bill_anchor, self.inc_anchor):
            try:
                entry.configure(
                    background=bg,
                    foreground=fg,
                    headersbackground=headersbg,
                    headersforeground=headersfg,
                    selectbackground="#3B82F6",
                    selectforeground="white"
                )
            except Exception:
                pass

    def _style_scrollbars(self):
        style = ttk.Style()
        is_dark = self.theme_var.get() == "Dark"
        
        if is_dark:
            bg = "#555555"
            trough = "#1f1f1f"
            arrow = "#555555"
            thumb = "#555555"
            active = "#777777"
        else:
            bg = "#F0F2F5"
            trough = "#E5E7EB"
            arrow = "#9CA3AF"
            thumb = "#9CA3AF"
            active = "#6B7280"

        style.configure("Vertical.TScrollbar",
                        background=thumb,
                        troughcolor=trough,
                        arrowcolor=arrow,
                        bordercolor=bg,
                        lightcolor=bg,
                        darkcolor=bg,
                        arrowsize=14)

        style.map("Vertical.TScrollbar",
                background=[("active", active), ("pressed", active)],
                arrowcolor=[("active", "#ffffff" if is_dark else "#374151")])

    def show_shortcuts(self):
        win = ctk.CTkToplevel(self)
        win.title("Tips & Shortcuts")
        win.geometry("840x640")
        win.minsize(600, 480)
        win.resizable(True, True)
        win.transient(self)
        win.grab_set()

        win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 840) // 2
        y = self.winfo_y() + (self.winfo_height() - 640) // 2
        win.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            win, text="Tips & Shortcuts",
            font=ctk.CTkFont(family="Verdana", size=18, weight="bold")
        ).pack(pady=(18, 10))

        frame = ctk.CTkScrollableFrame(win, width=800, height=480)
        frame.pack(padx=16, pady=(0, 8), fill="both", expand=True)

        frame.grid_columnconfigure(0, minsize=170)
        frame.grid_columnconfigure(1, weight=1)

        shortcuts = [
            ("Ctrl + S", "Save Inputs"),
            ("Delete", "Delete selected expense or income"),
            ("Shift + ↑", "Move selected expense/income up"),
            ("Shift + ↓", "Move selected expense/income down"),
            ("↑ / ↓", "Navigate selection in the list (normal)"),
            ("Drag & Drop", "Reorder expenses or incomes with the mouse"),
            ("Double-click row", "Toggle Paid / Unpaid in Projection"),
            ("Click treemap block", "Highlight matching rows in Projection"),
        ]

        for i, (key, desc) in enumerate(shortcuts):
            ctk.CTkLabel(
                frame, text=key,
                font=ctk.CTkFont(family="Verdana", size=13, weight="bold"),
                anchor="w"
            ).grid(row=i, column=0, sticky="w", padx=(12, 16), pady=5)

            ctk.CTkLabel(
                frame, text=desc,
                font=ctk.CTkFont(family="Verdana", size=13),
                anchor="w",
                justify="left",
                wraplength=580
            ).grid(row=i, column=1, sticky="w", padx=(0, 12), pady=5)

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=(4, 16))

        ctk.CTkButton(
            btn_frame, text="Close", width=110, height=34,
            command=win.destroy,
            font=ctk.CTkFont(family="Verdana", size=13)
        ).pack()

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

        if not acquire_lock(name):
            messagebox.showerror(
                "Budget already open",
                f"The budget file “{name}” is already open in another window.\n\n"
                "Please close the other instance first."
            )
            return

        release_lock(CURRENT_DB)

        if self.projection_win and self.projection_win.winfo_exists():
            self._on_projection_close()

        CURRENT_DB = name
        save_last_budget(name)
        init_database()
        self.title(f"Personal Budget Tracker — {CURRENT_DB}  (v{__version__})")
        self.load_inputs()
        self.load_bills()
        self.load_incomes()
        self.bill_category.configure(values=self.get_categories())
        self.update_dashboard()
        self.status_label.configure(text=f"Loaded {CURRENT_DB}", text_color="#9ece6a")

    def on_closing(self):
        release_lock(CURRENT_DB)
        try:
            self.save_column_widths(self.tree, "bills_col_widths")
            self.save_column_widths(self.inc_tree, "incomes_col_widths")
        except Exception:
            pass

        if self.projection_win is not None:
            try:
                self._on_projection_close()
            except Exception:
                pass

        try:
            for after_id in self.tk.call("after", "info"):
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            plt.close("all")
        except Exception:
            pass

        try:
            self.destroy()
        except Exception:
            pass

        sys.exit(0)

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
            except Exception:
                pass

        for col, width in defaults.items():
            tree.column(col, width=width)

    def create_widgets(self):
        top = ctk.CTkFrame(self, height=52, corner_radius=0,
                           fg_color=("#D1D5DB", "#2b2b2b"))
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="Personal Budget Tracker",
                     font=ctk.CTkFont(family="Verdana", size=20, weight="bold")).pack(side="left", padx=20)

        theme_frame = ctk.CTkFrame(top, fg_color="transparent")
        theme_frame.pack(side="right", padx=20)
        ctk.CTkLabel(theme_frame, text="Theme:", font=ctk.CTkFont(family="Verdana", size=13)).pack(side="left", padx=(0, 8))

        self.theme_var = ctk.StringVar(value=self.last_theme)

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

        self.left_frame = ctk.CTkFrame(self.main_container, width=280, corner_radius=12,
                                       border_width=1, border_color=("#d0d0d0", "#555555"))
        self.left_frame.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        self.left_frame.grid_propagate(False)

        ctk.CTkLabel(self.left_frame, text="Account Snapshot",
                     font=ctk.CTkFont(family="Verdana", size=20, weight="bold")).pack(pady=(16, 12))

        form = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        form.pack(padx=14, pady=4)

        ctk.CTkLabel(form, text="Current Balance ($):", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=0, padx=6, pady=8, sticky="e")
        self.balance_entry = ctk.CTkEntry(form, width=130, height=32, corner_radius=8, font=ctk.CTkFont(family="Verdana", size=12))
        self.balance_entry.grid(row=0, column=1, padx=6, pady=8)

        ctk.CTkLabel(form, text="As of Date:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=0, padx=6, pady=8, sticky="e")
        self.asof_entry = DateEntry(form, width=12, background="#2b2b2b", foreground="white",
                                    borderwidth=2, date_pattern="yyyy-mm-dd", font=("Verdana", 11))
        self.asof_entry.grid(row=1, column=1, padx=6, pady=8, sticky="w")
        self._fix_dateentry(self.asof_entry)

        ctk.CTkLabel(form, text="Safety Buffer ($):", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=2, column=0, padx=6, pady=8, sticky="e")
        self.buffer_entry = ctk.CTkEntry(form, width=130, height=32, corner_radius=8, font=ctk.CTkFont(family="Verdana", size=12))
        self.buffer_entry.grid(row=2, column=1, padx=6, pady=8)

        ctk.CTkButton(self.left_frame, text="Save Inputs", command=self.save_inputs,
                      width=180, height=38, corner_radius=8,
                      font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(pady=(12, 8))

        dash = ctk.CTkFrame(self.left_frame, corner_radius=8,
                            border_width=1, border_color=("#d0d0d0", "#555555"))
        dash.pack(fill="x", padx=10, pady=(4, 12))

        ctk.CTkLabel(dash, text="Quick Overview",
                     font=ctk.CTkFont(family="Verdana", size=14, weight="bold")).pack(pady=(8, 4))

        self.dash_safe_label = ctk.CTkLabel(dash, text="Safe to Spend: —",
                                            font=ctk.CTkFont(family="Verdana", size=13, weight="bold"))
        self.dash_safe_label.pack(anchor="w", padx=10, pady=(0, 4))

        WidgetTooltip(
            self.dash_safe_label,
            "Safe to Spend is the money you can freely use until your next Main income payday\n"
            "(or the custom End Date you set) while still protecting your Safety Buffer."
        )

        self.dash_bills_frame = ctk.CTkFrame(dash, fg_color="transparent")
        self.dash_bills_frame.pack(fill="x", padx=8, pady=(0, 8))

        self.right_frame = ctk.CTkFrame(self.main_container, corner_radius=12,
                                        border_width=1, border_color=("#d0d0d0", "#555555"))
        self.right_frame.grid(row=0, column=1, sticky="nsew")

        self.tabview = ctk.CTkTabview(
            self.right_frame,
            corner_radius=12,
            border_width=0
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.tabview.add("Expenses")
        self.tabview.add("Incomes")

        # ---------- EXPENSES TAB ----------
        bills_tab = self.tabview.tab("Expenses")

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
        self.bill_freq = ctk.CTkComboBox(add_frame, values=EXPENSE_FREQ_OPTIONS,
                                         width=120, height=30, corner_radius=6,
                                         command=self.on_frequency_change,
                                         font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_freq.set("Monthly")
        self.bill_freq.grid(row=1, column=1, padx=6, pady=5)

        ctk.CTkLabel(add_frame, text="Next Due Date:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=2, padx=6, pady=5, sticky="e")
        self.bill_anchor = DateEntry(add_frame, width=14, background="#2b2b2b", foreground="white",
                                     borderwidth=2, date_pattern="yyyy-mm-dd", font=("Verdana", 11))
        self.bill_anchor.grid(row=1, column=3, padx=6, pady=5, sticky="w")
        self._fix_dateentry(self.bill_anchor)

        self.bill_month_label = ctk.CTkLabel(add_frame, text="Quarter Cycle:", font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_month_label.grid(row=1, column=4, padx=6, pady=5, sticky="e")
        self.bill_month = ctk.CTkComboBox(add_frame, values=QUARTER_OPTIONS, width=160, height=30,
                                          font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_month.set("Jan / Apr / Jul / Oct")
        self.bill_month.grid(row=1, column=5, padx=6, pady=5)

        ctk.CTkLabel(add_frame, text="Notes:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=2, column=0, padx=6, pady=5, sticky="e")
        self.bill_notes_entry = ctk.CTkEntry(add_frame, width=520, height=30, corner_radius=6,
                                             font=ctk.CTkFont(family="Verdana", size=12))
        self.bill_notes_entry.grid(row=2, column=1, columnspan=5, padx=6, pady=5, sticky="w")

        btn_frame = ctk.CTkFrame(add_frame, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=6, pady=12)

        self.add_btn = ctk.CTkButton(btn_frame, text="Add Expense", command=self.add_bill, width=120, height=32, corner_radius=8,
                                     fg_color="#2E7D32", hover_color="#1B5E20",
                                     font=ctk.CTkFont(family="Verdana", size=12, weight="bold"))
        self.add_btn.pack(side="left", padx=5)

        self.update_bill_btn = ctk.CTkButton(btn_frame, text="Update Expense", command=self.update_bill, width=130, height=32,
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

        def get_bill_note(item):
            vals = self.tree.item(item, "values")
            if vals:
                return self.bill_notes.get(vals[0], "")
            return ""
        TreeviewTooltip(self.tree, get_bill_note)

        self.tree.bind("<Delete>", lambda e: self.delete_bill())
        self.tree.bind("<Shift-Up>", lambda e: self.move_bill_up())
        self.tree.bind("<Shift-Down>", lambda e: self.move_bill_down())
        self.tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release_bills)

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
                                        values=["Fixed", "Variable", "Hourly", "Passive"],
                                        width=120, height=30,
                                        command=self.on_income_type_change,
                                        font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_type.set("Fixed")
        self.inc_type.grid(row=0, column=3, padx=6, pady=5)

        self.star_btn = ctk.CTkButton(inc_frame, text="☆", width=36, height=30,
                                      font=ctk.CTkFont(size=16),
                                      fg_color="transparent", hover_color=("#e0e0e0", "#3a3a3a"),
                                      command=self.toggle_main_star)
        self.star_btn.grid(row=0, column=4, padx=(4, 0), pady=5)
        self.star_btn.grid_remove()
        WidgetTooltip(self.star_btn, "Mark as your main income source")

        ctk.CTkLabel(inc_frame, text="Amount / Rate:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=0, column=5, padx=6, pady=5, sticky="e")
        self.inc_amount = ctk.CTkEntry(inc_frame, width=110, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_amount.grid(row=0, column=6, padx=6, pady=5)

        self.inc_hours_label = ctk.CTkLabel(inc_frame, text="Hours:", font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_hours_label.grid(row=1, column=0, padx=6, pady=5, sticky="e")
        self.inc_hours = ctk.CTkEntry(inc_frame, width=150, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_hours.grid(row=1, column=1, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Frequency:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=2, padx=6, pady=5, sticky="e")
        self.inc_freq = ctk.CTkComboBox(inc_frame, values=NORMAL_FREQ_OPTIONS, width=120, height=30,
                                        command=self.on_income_freq_change,
                                        font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_freq.set("Monthly")
        self.inc_freq.grid(row=1, column=3, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Next Date:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=1, column=5, padx=6, pady=5, sticky="e")
        self.inc_anchor = DateEntry(inc_frame, width=14, background="#2b2b2b", foreground="white",
                                    borderwidth=2, date_pattern="yyyy-mm-dd", font=("Verdana", 11))
        self.inc_anchor.grid(row=1, column=6, padx=6, pady=5, sticky="w")
        self._fix_dateentry(self.inc_anchor)

        self.inc_month_label = ctk.CTkLabel(inc_frame, text="Quarter Cycle:", font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_month_label.grid(row=2, column=2, padx=6, pady=5, sticky="e")
        self.inc_month = ctk.CTkComboBox(inc_frame, values=QUARTER_OPTIONS, width=160, height=30,
                                         font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_month.set("Jan / Apr / Jul / Oct")
        self.inc_month.grid(row=2, column=3, padx=6, pady=5)

        ctk.CTkLabel(inc_frame, text="Notes:", font=ctk.CTkFont(family="Verdana", size=12)).grid(row=3, column=0, padx=6, pady=5, sticky="e")
        self.inc_notes_entry = ctk.CTkEntry(inc_frame, width=520, height=30, corner_radius=6, font=ctk.CTkFont(family="Verdana", size=12))
        self.inc_notes_entry.grid(row=3, column=1, columnspan=6, padx=6, pady=5, sticky="w")

        inc_btn_frame = ctk.CTkFrame(inc_frame, fg_color="transparent")
        inc_btn_frame.grid(row=4, column=0, columnspan=7, pady=10)

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

        inc_cols = ("id", "name", "type", "amount", "primary", "frequency", "next")
        self.inc_tree = ttk.Treeview(inc_table_frame, columns=inc_cols, show="headings", height=10)

        defaults_inc = {
            "id": 60, "name": 150, "type": 100, "amount": 90,
            "primary": 70, "frequency": 100, "next": 110
        }

        for c, h in zip(inc_cols, ["ID", "Name", "Type", "Amount", "Main", "Frequency", "Next Date"]):
            self.inc_tree.heading(c, text=h)
            self.inc_tree.column(c, width=defaults_inc[c], anchor="center")

        self.load_column_widths(self.inc_tree, "incomes_col_widths", defaults_inc)
        self.inc_tree.bind("<ButtonRelease-1>", lambda e: self.save_column_widths(self.inc_tree, "incomes_col_widths"))

        inc_scroll = ttk.Scrollbar(inc_table_frame, orient="vertical", command=self.inc_tree.yview)
        self.inc_tree.configure(yscrollcommand=inc_scroll.set)
        self.inc_tree.pack(side="left", fill="both", expand=True)
        inc_scroll.pack(side="right", fill="y")

        def get_inc_note(item):
            vals = self.inc_tree.item(item, "values")
            if vals:
                return self.inc_notes.get(vals[0], "")
            return ""
        TreeviewTooltip(self.inc_tree, get_inc_note)

        self.inc_tree.bind("<Delete>", lambda e: self.delete_income())
        self.inc_tree.bind("<Shift-Up>", lambda e: self.move_income_up())
        self.inc_tree.bind("<Shift-Down>", lambda e: self.move_income_down())
        self.inc_tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.inc_tree.bind("<B1-Motion>", self._on_drag_motion)
        self.inc_tree.bind("<ButtonRelease-1>", self._on_drag_release_incomes)

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

    def _fix_dateentry(self, entry):
        def apply_fix():
            try:
                if hasattr(entry, "_top_cal") and entry._top_cal.winfo_exists():
                    cal = entry._top_cal
                    cal.overrideredirect(False)
                    cal.attributes("-topmost", True)
                    cal.lift()
                    cal.focus_force()
                    cal.protocol("WM_DELETE_WINDOW", lambda: None)
            except Exception:
                pass

        def on_open(event=None):
            entry.after(30, apply_fix)

        entry.bind("<Button-1>", on_open, add="+")
        entry.bind("<FocusIn>", on_open, add="+")
        entry.bind("<<DateEntryPopup>>", on_open, add="+")

    # ------------------------------------------------------------------
    # Drag-and-drop helpers
    # ------------------------------------------------------------------
    def _on_drag_start(self, event):
        tree = event.widget
        item = tree.identify_row(event.y)
        if item:
            self.drag_item = item
            self.drag_tree = tree
            tree.selection_set(item)

    def _on_drag_motion(self, event):
        pass

    def _on_drag_release_bills(self, event):
        self._finish_drag(event, is_bill=True)

    def _on_drag_release_incomes(self, event):
        self._finish_drag(event, is_bill=False)

    def _finish_drag(self, event, is_bill=True):
        if not self.drag_item or self.drag_tree is None:
            self.drag_item = None
            self.drag_tree = None
            return

        tree = self.drag_tree
        target = tree.identify_row(event.y)

        if is_bill:
            self.save_column_widths(self.tree, "bills_col_widths")
        else:
            self.save_column_widths(self.inc_tree, "incomes_col_widths")

        if not target or target == self.drag_item:
            self.drag_item = None
            self.drag_tree = None
            return

        children = list(tree.get_children())
        try:
            from_idx = children.index(self.drag_item)
            to_idx = children.index(target)
        except ValueError:
            self.drag_item = None
            self.drag_tree = None
            return

        item = children.pop(from_idx)
        children.insert(to_idx, item)

        new_order_ids = []
        for iid in children:
            vals = tree.item(iid, "values")
            if vals:
                new_order_ids.append(int(vals[0]))

        with get_db() as conn:
            cur = conn.cursor()
            table = "bills" if is_bill else "incomes"
            for order, db_id in enumerate(new_order_ids):
                cur.execute(f"UPDATE {table} SET sort_order=? WHERE id=?", (order, db_id))
            conn.commit()

        self.drag_item = None
        self.drag_tree = None

        if is_bill:
            self.load_bills()
        else:
            self.load_incomes()

    # ------------------------------------------------------------------
    # Theme / form helpers
    # ------------------------------------------------------------------
    def change_theme(self, choice):
        self.apply_theme(choice)
        self.update_dashboard()

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        ("theme", choice))
            conn.commit()

    def apply_theme(self, theme):
        style = ttk.Style()
        style.theme_use("clam")
        self._style_scrollbars()
        self._style_dateentries()

        if theme == "Light":
            ctk.set_appearance_mode("Light")
            bg_color = "#E8EAED"
            soft_card = "#F0F2F5"
            border_color = "#D1D5DB"
            text_color = "#1F2937"
            heading_bg = "#D1D5DB"
            self.configure(fg_color=bg_color)

            style.configure("Treeview",
                            background=soft_card,
                            foreground=text_color,
                            fieldbackground=soft_card,
                            font=("Verdana", 11),
                            rowheight=26,
                            borderwidth=0,
                            relief="flat")

            style.configure("Treeview.Heading",
                            background=heading_bg,
                            foreground=text_color,
                            font=("Verdana", 11, "bold"),
                            borderwidth=1,
                            relief="flat")

            style.map("Treeview.Heading",
                    background=[("active", "#C5CAD3")])

            self.tabview._segmented_button.configure(
                fg_color="#E5E7EB",
                selected_color="#3B82F6",
                unselected_color="#9CA3AF",
                text_color="#1F2937",
                selected_hover_color="#2563EB",
                unselected_hover_color="#6B7280",
                font=ctk.CTkFont(family="Verdana", size=15, weight="bold"),
                corner_radius=10,
                border_width=0
            )
            try:
                self.left_frame.configure(fg_color=soft_card, border_color=border_color)
                self.right_frame.configure(fg_color=soft_card, border_color=border_color)
                self.main_container.configure(fg_color=bg_color)
            except Exception:
                pass
        else:
            ctk.set_appearance_mode("Dark")
            self.configure(fg_color="#1a1a1a")
            
            style.configure("Treeview",
                            background="#2b2b2b",
                            foreground="#e0e0e0",
                            fieldbackground="#2b2b2b",
                            font=("Verdana", 11),
                            rowheight=26,
                            borderwidth=0,
                            relief="flat")

            style.configure("Treeview.Heading",
                            background="#3c3c3c",
                            foreground="#e0e0e0",
                            font=("Verdana", 11, "bold"),
                            borderwidth=1,
                            relief="flat")

            style.map("Treeview.Heading",
                    background=[("active", "#4a4a4a")])
            
            self.tabview._segmented_button.configure(
                fg_color="#2b2b2b",
                selected_color="#1F6AA5",
                unselected_color="#333333",
                text_color="#ffffff",
                selected_hover_color="#144870",
                unselected_hover_color="#404040",
                font=ctk.CTkFont(family="Verdana", size=15, weight="bold"),
                corner_radius=10,
                border_width=0
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

        if choice == "Fixed":
            self.star_btn.grid()
            self._update_star_visual()
        else:
            self.star_btn.grid_remove()
            self.form_is_main = False
            self._update_star_visual()

        self.on_income_freq_change(self.inc_freq.get())

    def on_income_freq_change(self, choice):
        if choice in ("Weekly", "Bi-weekly", "Monthly", "Quarterly", "One-time"):
            self.inc_anchor.configure(state="normal")
        else:
            self.inc_anchor.configure(state="disabled")

        if choice == "Quarterly":
            self.inc_month_label.grid()
            self.inc_month.grid()
        else:
            self.inc_month_label.grid_remove()
            self.inc_month.grid_remove()

    def toggle_main_star(self):
        if not self.form_is_main:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, name FROM incomes WHERE is_primary=1")
                existing = cur.fetchone()
            if existing and (self.editing_income_id is None or existing[0] != self.editing_income_id):
                if not messagebox.askyesno(
                    "Main Income",
                    f"Only one income can be marked as Main.\n\n"
                    f"“{existing[1]}” is currently Main.\n\n"
                    f"Do you want to make this the new Main income?"
                ):
                    return
            self.form_is_main = True
        else:
            self.form_is_main = False
        self._update_star_visual()

    def _update_star_visual(self):
        if self.form_is_main:
            self.star_btn.configure(text="★", text_color="#FBBF24")
        else:
            self.star_btn.configure(text="☆", text_color=("gray40", "gray70"))

    def get_quarter_start(self, widget):
        return QUARTER_MAP.get(widget.get(), 1)

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
                                   f"Delete “{name}”?\n(Existing expenses keep the old name.)",
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
            except Exception:
                self.asof_entry.set_date(today)
            self.buffer_entry.delete(0, "end")
            self.buffer_entry.insert(0, str(row[2] if row[2] is not None else 500))
        else:
            self.asof_entry.set_date(today)
            self.buffer_entry.insert(0, "500")

    def clear_bill_form(self):
        self.bill_name.delete(0, "end")
        self.bill_amount.delete(0, "end")
        self.bill_notes_entry.delete(0, "end")
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
            notes = self.bill_notes_entry.get().strip()

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COALESCE(MAX(sort_order), 0) FROM bills")
                max_order = cur.fetchone()[0]
                cur.execute("""INSERT INTO bills
                    (name, amount, due_day, category, frequency, month, anchor_date, sort_order, notes)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (name, amount, due_day, category, freq, month, anchor_date, max_order + 1, notes))
                conn.commit()

            self.clear_bill_form()
            self.load_bills()
            self.update_dashboard()
            self.status_label.configure(text=f"Added expense '{name}'", text_color="#9ece6a")
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
            cur.execute("SELECT name, amount, category, frequency, month, anchor_date, notes FROM bills WHERE id=?", (vals[0],))
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
            except Exception:
                pass

        self.bill_notes_entry.delete(0, "end")
        if row[6]:
            self.bill_notes_entry.insert(0, row[6])

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
            notes = self.bill_notes_entry.get().strip()

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""UPDATE bills SET
                    name=?, amount=?, due_day=?, category=?, frequency=?, month=?, anchor_date=?, notes=?
                    WHERE id=?""",
                    (name, amount, due_day, category, freq, month, anchor_date, notes, self.editing_id))
                conn.commit()

            self.clear_bill_form()
            self.load_bills()
            self.update_dashboard()
            self.status_label.configure(text=f"Updated expense '{name}'", text_color="#9ece6a")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def cancel_edit(self):
        self.clear_bill_form()

    def load_bills(self):
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT id, name, amount, category, frequency, anchor_date, month, notes
                           FROM bills ORDER BY sort_order, id""")
            self.all_bills = cur.fetchall()
        self.bill_notes = {r[0]: (r[7] or "") for r in self.all_bills}
        self._do_filter_bills()

    def filter_bills(self, *args):
        if self._search_after_id:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.after(250, self._do_filter_bills)

    def _do_filter_bills(self):
        search = self.search_var.get().lower().strip()
        for i in self.tree.get_children():
            self.tree.delete(i)
        for row in getattr(self, "all_bills", []):
            if search in str(row[1]).lower() or search in str(row[3] or "").lower() or not search:
                r = list(row[:7])
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
        if messagebox.askyesno("Confirm", f"Delete expense '{vals[1]}'?"):
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
            except Exception:
                pass
        self.load_bills()

    def clear_income_form(self):
        self.inc_name.delete(0, "end")
        self.inc_amount.delete(0, "end")
        self.inc_hours.delete(0, "end")
        self.inc_notes_entry.delete(0, "end")
        self.inc_type.set("Fixed")
        self.inc_freq.set("Monthly")
        self.inc_month.set("Jan / Apr / Jul / Oct")
        self.form_is_main = False
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
            is_primary = 1 if self.form_is_main else 0
            freq = self.inc_freq.get()
            month = self.get_quarter_start(self.inc_month) if freq == "Quarterly" else None

            if freq in ("Weekly", "Bi-weekly", "Monthly", "Quarterly", "One-time"):
                anchor_dt = self._get_valid_date(self.inc_anchor, "Next Date")
                if anchor_dt is None:
                    return
                anchor = anchor_dt.strftime("%Y-%m-%d")
                due_day = anchor_dt.day
            else:
                anchor = None
                due_day = None

            with get_db() as conn:
                cur = conn.cursor()
                if is_primary:
                    cur.execute("UPDATE incomes SET is_primary=0")
                cur.execute("SELECT COALESCE(MAX(sort_order), 0) FROM incomes")
                max_order = cur.fetchone()[0]
                cur.execute("""INSERT INTO incomes
                    (name, type, amount, hours, frequency, due_day, month, notes,
                     sort_order, is_primary, anchor_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (name, self.inc_type.get(), amount, hours, freq, due_day, month,
                     self.inc_notes_entry.get().strip(), max_order + 1, is_primary, anchor))
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
                                  notes, is_primary, anchor_date
                           FROM incomes WHERE id=?""", (vals[0],))
            row = cur.fetchone()

        if not row:
            return

        self.inc_name.delete(0, "end")
        self.inc_name.insert(0, row[0])
        self.inc_type.set(row[1] if row[1] in ("Fixed", "Variable", "Hourly", "Passive") else "Fixed")
        self.on_income_type_change(self.inc_type.get())

        self.inc_amount.delete(0, "end")
        self.inc_amount.insert(0, row[2])

        self.inc_hours.delete(0, "end")
        if row[3] is not None:
            self.inc_hours.insert(0, row[3])

        self.inc_freq.set(row[4] or "Monthly")
        self.on_income_freq_change(self.inc_freq.get())

        if row[6] is not None:
            self.inc_month.set(REVERSE_QUARTER_MAP.get(row[6], "Jan / Apr / Jul / Oct"))

        self.inc_notes_entry.delete(0, "end")
        if row[7]:
            self.inc_notes_entry.insert(0, row[7])

        self.form_is_main = bool(row[8])
        self._update_star_visual()

        if row[9]:
            try:
                self.inc_anchor.set_date(datetime.strptime(row[9], "%Y-%m-%d").date())
            except Exception:
                pass

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
            is_primary = 1 if self.form_is_main else 0
            freq = self.inc_freq.get()
            month = self.get_quarter_start(self.inc_month) if freq == "Quarterly" else None

            if freq in ("Weekly", "Bi-weekly", "Monthly", "Quarterly", "One-time"):
                anchor_dt = self._get_valid_date(self.inc_anchor, "Next Date")
                if anchor_dt is None:
                    return
                anchor = anchor_dt.strftime("%Y-%m-%d")
                due_day = anchor_dt.day
            else:
                anchor = None
                due_day = None

            with get_db() as conn:
                cur = conn.cursor()
                if is_primary:
                    cur.execute("UPDATE incomes SET is_primary=0")
                cur.execute("""UPDATE incomes SET
                    name=?, type=?, amount=?, hours=?, frequency=?, due_day=?, month=?, notes=?,
                    is_primary=?, anchor_date=?
                    WHERE id=?""",
                    (name, self.inc_type.get(), amount, hours, freq, due_day, month,
                     self.inc_notes_entry.get().strip(), is_primary, anchor, self.editing_income_id))
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
        self.inc_notes = {}
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT id, name, type, amount, is_primary, frequency, anchor_date, notes
                           FROM incomes ORDER BY is_primary DESC, sort_order, id""")
            for row in cur.fetchall():
                primary_str = "★" if row[4] else ""
                next_str = row[6] or ""
                self.inc_notes[row[0]] = row[7] or ""
                self.inc_tree.insert("", "end", values=(
                    row[0], row[1], row[2], row[3], primary_str, row[5], next_str
                ))

    def delete_income(self):
        sel = self.inc_tree.selection()
        if not sel:
            return
        vals = self.inc_tree.item(sel[0])["values"]
        if messagebox.askyesno("Confirm", f"Delete income '{vals[1]}'?"):
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
            except Exception:
                pass
        self.load_incomes()

    def update_dashboard(self):
        for w in self.dash_bills_frame.winfo_children():
            w.destroy()

        data = self._generate_projection_data(silent=True)
        if not data:
            self.dash_safe_label.configure(text="Safe to Spend: (save inputs first)", text_color="gray")
            return

        safe = data["safe"]
        safe_color = "#2E7D32" if self.theme_var.get() == "Light" else "#9ece6a"
        color = safe_color if safe >= 0 else "#ff5c5c"
        self.dash_safe_label.configure(text=f"Safe to Spend: ${safe:,.2f}", text_color=color)

        upcoming = []
        for t in data["full_tx"]:
            if t["date"] >= data["as_of"] and t["expense"] > 0 and not t["is_paid"]:
                upcoming.append(t)
                if len(upcoming) >= 3:
                    break

        if not upcoming:
            ctk.CTkLabel(self.dash_bills_frame, text="No upcoming unpaid expenses",
                         font=ctk.CTkFont(family="Verdana", size=12), text_color="gray").pack(anchor="w")
        else:
            ctk.CTkLabel(self.dash_bills_frame, text="Next expenses:",
                         font=ctk.CTkFont(family="Verdana", size=12, weight="bold")).pack(anchor="w")
            for t in upcoming:
                txt = f"{t['date']}  {t['desc'][:16]}  ${t['expense']:,.0f}"
                ctk.CTkLabel(self.dash_bills_frame, text=txt,
                             font=ctk.CTkFont(family="Verdana", size=12)).pack(anchor="w")

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

            cur.execute("""SELECT name, amount, frequency, anchor_date
                           FROM incomes WHERE is_primary=1 LIMIT 1""")
            primary = cur.fetchone()

            cur.execute("""SELECT name, type, amount, hours, frequency, due_day, month, is_primary, anchor_date, notes
                           FROM incomes ORDER BY sort_order, id""")
            income_rows = cur.fetchall()

            cur.execute("""SELECT name, amount, due_day, category, frequency, month, anchor_date, notes
                           FROM bills ORDER BY sort_order, id""")
            bill_rows = cur.fetchall()

            cur.execute("SELECT date, description FROM paid_transactions")
            previously_paid = {f"{d}|{desc}" for d, desc in cur.fetchall()}

        month_start = as_of.replace(day=1)
        lookback = min(as_of - timedelta(days=10), month_start - timedelta(days=40))
        end_date = as_of + relativedelta(months=12)

        all_paychecks = []
        pay_amt = 0.0
        next_pay = as_of + timedelta(days=14)

        if primary:
            _, pay_amt, schedule, anchor_str = primary
            pay_amt = float(pay_amt or 0)
            try:
                next_pay = datetime.strptime(anchor_str, "%Y-%m-%d").date()
            except Exception:
                next_pay = as_of

            freq = (schedule or "Monthly").lower()
            try:
                anchor = datetime.strptime(anchor_str, "%Y-%m-%d").date()
            except Exception:
                anchor = as_of

            if freq == "bi-weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=14)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        all_paychecks.append(d)
                    d += timedelta(days=14)
            elif freq == "weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=7)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        all_paychecks.append(d)
                    d += timedelta(days=7)
            else:
                d = anchor
                for _ in range(3):
                    d = d - relativedelta(months=1)
                while d <= end_date:
                    due = date(d.year, d.month, min(anchor.day, calendar.monthrange(d.year, d.month)[1]))
                    if lookback <= due <= end_date:
                        all_paychecks.append(due)
                    d = d + relativedelta(months=1)

            all_paychecks = sorted(set(all_paychecks))
            future = [d for d in all_paychecks if d >= as_of]
            if future:
                next_pay = min(future)

        if self.safe_end_date is None:
            self.safe_end_date = next_pay
        end = self.safe_end_date

        tx = []

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
                    "is_paid": paid,
                    "notes": ""
                })

        def make_due(year, month, day):
            last = calendar.monthrange(year, month)[1]
            return date(year, month, min(day, last))

        for name, typ, amount, hours, freq, due_day, month, is_prim, anchor_date, notes in income_rows:
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
            except Exception:
                continue

            day = anchor.day
            start_month = int(month) if month else 1
            dates = []
            freq_l = (freq or "").lower()

            if freq_l == "one-time":
                if lookback <= anchor <= end_date:
                    dates.append(anchor)
            elif freq_l == "weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=7)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        dates.append(d)
                    d += timedelta(days=7)
            elif freq_l == "bi-weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=14)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        dates.append(d)
                    d += timedelta(days=14)
            elif freq_l == "monthly":
                d = anchor
                for _ in range(3):
                    d = d - relativedelta(months=1)
                while d <= end_date:
                    due = make_due(d.year, d.month, day)
                    if lookback <= due <= end_date:
                        dates.append(due)
                    d = d + relativedelta(months=1)
            elif freq_l == "quarterly":
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
                    "is_paid": paid,
                    "notes": notes or ""
                })

        for name, amount, due_day, category, frequency, month, anchor_date, notes in bill_rows:
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
            except Exception:
                continue

            dates = []

            if freq == "one-time":
                if lookback <= anchor <= end_date:
                    dates.append(anchor)
            elif freq == "weekly":
                d = anchor
                while d > lookback:
                    d -= timedelta(days=7)
                while d <= end_date:
                    if lookback <= d <= end_date:
                        dates.append(d)
                    d += timedelta(days=7)
            elif freq == "bi-weekly":
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
                    "is_paid": paid,
                    "notes": notes or ""
                })

        tx.sort(key=lambda x: x["date"])

        full_tx = tx[:]
        tx = [t for t in full_tx if t["date"] >= month_start]

        def unpaid_expense(t):
            return t["expense"] if not t["is_paid"] else 0.0

        def unpaid_income(t):
            return t["income"] if not t["is_paid"] else 0.0

        if end == next_pay:
            bills_in_window = sum(unpaid_expense(t) for t in full_tx if as_of <= t["date"] < next_pay)
            income_in_window = 0.0
            bal_after = current_balance - bills_in_window + pay_amt
            bal_label = "Balance after next pay"
            period_label = f"Next Pay ({next_pay})"
        else:
            bills_in_window = sum(unpaid_expense(t) for t in full_tx if as_of <= t["date"] <= end)
            income_in_window = sum(unpaid_income(t) for t in full_tx if as_of <= t["date"] <= end)
            bal_after = current_balance - bills_in_window + income_in_window
            bal_label = f"Balance after {end}"
            period_label = f"Until {end}"

        safe = current_balance - bills_in_window + income_in_window - buffer

        after_bills = []
        for t in full_tx:
            if t["expense"] > 0 and not t["is_paid"] and next_pay < t["date"] <= end:
                after_bills.append(t)
        after_bills.sort(key=lambda x: x["expense"], reverse=True)

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
            "safe_end": end,
            "after_bills": after_bills,
            "month_options": month_options,
        }

    def _create_projection_window(self, data):
        win = ctk.CTkToplevel(self)
        win.title(f"Budget Projection — {CURRENT_DB}")
        x = self.winfo_x() + 80
        y = self.winfo_y() + 40
        win.geometry(f"1280x920+{x}+{y}")
        win.protocol("WM_DELETE_WINDOW", self._on_projection_close)

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
        try:
            if getattr(self, "_proj_canvas", None) is not None:
                try:
                    self._proj_canvas.get_tk_widget().destroy()
                except Exception:
                    pass
                self._proj_canvas = None
            if getattr(self, "_proj_fig", None) is not None:
                try:
                    plt.close(self._proj_fig)
                except Exception:
                    pass
                self._proj_fig = None

            if getattr(self, "_treemap_canvas", None) is not None:
                try:
                    self._treemap_canvas.get_tk_widget().destroy()
                except Exception:
                    pass
                self._treemap_canvas = None
            if getattr(self, "_treemap_fig", None) is not None:
                try:
                    plt.close(self._treemap_fig)
                except Exception:
                    pass
                self._treemap_fig = None
            if getattr(self, "_treemap_tip", None) is not None:
                try:
                    self._treemap_tip.destroy()
                except Exception:
                    pass
                self._treemap_tip = None
                self._treemap_tip_label = None
                self._treemap_after_id = None
            
        except Exception:
            pass

        if self.projection_win is not None:
            try:
                self.projection_win.destroy()
            except Exception:
                pass
        self.projection_win = None
        self.safe_end_date = None
        self._highlighted_category = None

    def _on_hide_paid_toggle(self):
        self.hide_paid = self.hide_paid_var.get()
        if self.projection_win and self.projection_win.winfo_exists():
            data = self._generate_projection_data(silent=True)
            if data:
                self._refresh_projection_window(data)

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

    def _highlight_category(self, category: str):
        if not hasattr(self, "proj_tree") or not self.proj_tree.winfo_exists():
            return

        self._clear_category_highlight()
        self._highlighted_category = category

        cutoff = getattr(self, "_treemap_cutoff", None)

        for item in self.proj_tree.get_children():
            vals = self.proj_tree.item(item, "values")
            if len(vals) < 3 or vals[2] != category:
                continue

            if cutoff is not None:
                try:
                    row_date = datetime.strptime(str(vals[0]), "%Y-%m-%d").date()
                    if not (cutoff - timedelta(days=30) <= row_date <= cutoff):
                        continue
                except Exception:
                    continue

            current_tags = list(self.proj_tree.item(item, "tags"))
            if "highlight" not in current_tags:
                current_tags.append("highlight")
            self.proj_tree.item(item, tags=current_tags)

        self.status_label.configure(
            text=f"Highlighted category: {category} (next 30 days)",
            text_color="#9ece6a"
        )

    def _clear_category_highlight(self):
        if not hasattr(self, "proj_tree") or not self.proj_tree.winfo_exists():
            return
        self._highlighted_category = None
        for item in self.proj_tree.get_children():
            current_tags = list(self.proj_tree.item(item, "tags"))
            if "highlight" in current_tags:
                current_tags.remove("highlight")
                self.proj_tree.item(item, tags=current_tags)
        self.status_label.configure(text="Ready", text_color="gray")

    def _draw_treemap(self, ax, categories, values, colors):
        total = sum(values)
        if total <= 0:
            return [], []

        sizes = [v / total for v in values]
        cats  = list(categories)
        cols  = list(colors)

        def worst(row, w):
            s = sum(row)
            if s <= 0 or w <= 0:
                return 1e9
            return max(max(w * w * r / (s * s), s * s / (w * w * r)) for r in row)

        rects = []
        x = y = 0.0
        remaining_width = 1.0
        remaining_height = 1.0
        i = 0
        n = len(sizes)

        while i < n:
            horizontal = remaining_width >= remaining_height
            length = remaining_width if horizontal else remaining_height

            row = [sizes[i]]
            j = i + 1
            while j < n:
                if worst(row + [sizes[j]], length) > worst(row, length):
                    break
                row.append(sizes[j])
                j += 1

            row_area = sum(row)

            if horizontal:
                h = row_area / remaining_width
                cx = x
                for s in row:
                    w = (s / row_area) * remaining_width
                    rects.append((cx, y, w, h))
                    cx += w
                y += h
                remaining_height -= h
            else:
                w = row_area / remaining_height
                cy = y
                for s in row:
                    h = (s / row_area) * remaining_height
                    rects.append((x, cy, w, h))
                    cy += h
                x += w
                remaining_width -= w

            i = j

        patches = []
        ordered_cats = []
        for idx, (rx, ry, rw, rh) in enumerate(rects):
            patch = mpatches.Rectangle(
                (rx, 1.0 - ry - rh), rw, rh,
                facecolor=cols[idx],
                edgecolor="#111111",
                linewidth=1.8,
                picker=8
            )
            ax.add_patch(patch)
            patches.append(patch)
            ordered_cats.append(cats[idx])

            pct = sizes[idx] * 100
            if rw > 0.11 and rh > 0.09:
                ax.text(rx + rw/2, 1.0 - ry - rh/2, f"{pct:.0f}%",
                        ha="center", va="center", fontsize=9,
                        fontweight="bold", color="#111111")

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("auto")
        ax.axis("off")
        return patches, ordered_cats

    def _build_projection_content(self, win, data):
        menubar = Menu(win)
        win.configure(menu=menubar)
        actions = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Actions", menu=actions)
        actions.add_command(label="Mark all past as paid", command=self._mark_past_paid)
        actions.add_command(label="Clear all paid flags", command=self._clear_all_paid)

        tx = data["tx"]
        full_tx = data["full_tx"]
        start_bal = data["start_bal"]
        as_of = data["as_of"]
        self._treemap_cutoff = as_of + timedelta(days=30)
        safe = data["safe"]
        bills_before = data["bills_before"]
        bal_after = data["bal_after"]
        bal_label = data["bal_label"]
        buffer = data["buffer"]
        cat_totals = data["cat_totals"]
        has_primary = data.get("has_primary", False)
        month_options = data["month_options"]
        next_pay = data["next_pay"]
        end = data["safe_end"]
        after_bills = data["after_bills"]

        # ========== HEADER ==========
        sum_frame = ctk.CTkFrame(win, corner_radius=10)
        sum_frame.pack(fill="x", padx=14, pady=(6, 4))

        sum_frame.grid_columnconfigure(0, minsize=210)
        sum_frame.grid_columnconfigure(1, minsize=240)
        sum_frame.grid_columnconfigure(2, minsize=280)
        sum_frame.grid_columnconfigure(3, minsize=230)

        # SAFE TO SPEND
        left = ctk.CTkFrame(sum_frame, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw", padx=(14, 10), pady=8)

        safe_title = ctk.CTkLabel(left, text="SAFE TO SPEND",
                    font=ctk.CTkFont(family="Verdana", size=13, weight="bold"))
        safe_title.pack(anchor="w")

        safe_color = "#2E7D32" if self.theme_var.get() == "Light" else "#9ece6a"
        color = safe_color if safe >= 0 else "#f7768e"

        safe_value = ctk.CTkLabel(left, text=f"${safe:,.2f}",
                    font=ctk.CTkFont(family="Verdana", size=26, weight="bold"),
                    text_color=color)
        safe_value.pack(anchor="w", pady=(2, 0))

        tooltip_text = (
            "Safe to Spend is the money you can freely use until your next Main income payday\n"
            "(or the custom End Date you set) while still protecting your Safety Buffer."
        )
        WidgetTooltip(safe_title, tooltip_text)
        WidgetTooltip(safe_value, tooltip_text)

        if safe < 0:
            ctk.CTkLabel(left, text=f"⚠ Buffer short (${buffer})",
                        text_color="#f7768e",
                        font=ctk.CTkFont(family="Verdana", size=12, weight="bold")).pack(anchor="w", pady=(2, 0))

        # End date controls
        cal = ctk.CTkFrame(sum_frame, fg_color="transparent")
        cal.grid(row=0, column=1, sticky="nw", padx=(0, 10), pady=8)

        ctk.CTkLabel(cal, text="End date:", font=ctk.CTkFont(family="Verdana", size=12)).pack(anchor="w")

        def days_in_month(year, month):
            return calendar.monthrange(year, month)[1]

        today = date.today()
        current_year = today.year
        default_date = end

        self.end_year_var = ctk.StringVar(value=str(default_date.year))
        self.end_month_var = ctk.StringVar(value=f"{default_date.month:02d}")
        self.end_day_var = ctk.StringVar(value=f"{default_date.day:02d}")

        def update_day_dropdown():
            try:
                y = int(self.end_year_var.get())
                m = int(self.end_month_var.get())
                max_day = days_in_month(y, m)
                day_values = [f"{i:02d}" for i in range(1, max_day + 1)]
                self.end_day_menu.configure(values=day_values)
                current_day = int(self.end_day_var.get())
                if current_day > max_day:
                    self.end_day_var.set(f"{max_day:02d}")
            except Exception:
                pass

        def apply_new_date():
            try:
                y = int(self.end_year_var.get())
                m = int(self.end_month_var.get())
                d = int(self.end_day_var.get())
                new_date = date(y, m, d)
                self.safe_end_date = new_date
                data = self._generate_projection_data(silent=True)
                if data:
                    self._refresh_projection_window(data)
                self.update_dashboard()
            except Exception:
                pass

        dropdown_frame = ctk.CTkFrame(cal, fg_color="transparent")
        dropdown_frame.pack(anchor="w", pady=(3, 2))

        self.end_year_menu = ctk.CTkOptionMenu(
            dropdown_frame, values=[str(current_year), str(current_year + 1)],
            variable=self.end_year_var, width=70, height=28,
            command=lambda _: update_day_dropdown(),
            font=ctk.CTkFont(family="Verdana", size=12)
        )
        self.end_year_menu.pack(side="left", padx=(0, 4))

        self.end_month_menu = ctk.CTkOptionMenu(
            dropdown_frame, values=[f"{i:02d}" for i in range(1, 13)],
            variable=self.end_month_var, width=60, height=28,
            command=lambda _: update_day_dropdown(),
            font=ctk.CTkFont(family="Verdana", size=12)
        )
        self.end_month_menu.pack(side="left", padx=(0, 4))

        self.end_day_menu = ctk.CTkOptionMenu(
            dropdown_frame, values=[f"{i:02d}" for i in range(1, 32)],
            variable=self.end_day_var, width=60, height=28,
            font=ctk.CTkFont(family="Verdana", size=12)
        )
        self.end_day_menu.pack(side="left")

        update_day_dropdown()

        btn_row = ctk.CTkFrame(cal, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(3, 0))

        ctk.CTkButton(btn_row, text="Apply Date", width=100, height=28,
                    command=apply_new_date,
                    font=ctk.CTkFont(family="Verdana", size=12, weight="bold")).pack(side="left", padx=(0, 6))

        ctk.CTkButton(btn_row, text="Reset", width=70, height=28,
                    command=lambda: (
                        self.end_year_var.set(str(next_pay.year)),
                        self.end_month_var.set(f"{next_pay.month:02d}"),
                        self.end_day_var.set(f"{next_pay.day:02d}"),
                        update_day_dropdown(),
                        apply_new_date()
                    ),
                    font=ctk.CTkFont(family="Verdana", size=12)).pack(side="left")

        self.hide_paid_var = ctk.BooleanVar(value=self.hide_paid)
        ctk.CTkCheckBox(cal, text="Hide paid items", variable=self.hide_paid_var,
                        command=self._on_hide_paid_toggle,
                        font=ctk.CTkFont(family="Verdana", size=12)).pack(anchor="w", pady=(4, 0))

        # Window info
        info = ctk.CTkFrame(sum_frame, fg_color="transparent")
        info.grid(row=0, column=2, sticky="nw", padx=(0, 10), pady=8)

        if has_primary:
            ctk.CTkLabel(info, text=f"Window: {data['period_label']}",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")
            ctk.CTkLabel(info, text=f"Expenses in window: ${bills_before:,.2f}",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")
            ctk.CTkLabel(info, text=f"+ Incomes: ${data['income_in_window']:,.2f}",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")
            ctk.CTkLabel(info, text=f"{bal_label}: ${bal_after:,.2f}",
                        font=ctk.CTkFont(family="Verdana", size=13)).pack(anchor="w")
        else:
            ctk.CTkLabel(info, text="No Main income set (star a Fixed income)",
                        text_color="#f7768e",
                        font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(anchor="w")

        # Expenses after next payday
        if end > next_pay and after_bills:
            warn = ctk.CTkFrame(sum_frame, fg_color="transparent")
            warn.grid(row=0, column=3, sticky="nw", padx=(0, 14), pady=8)

            warn_color = "#B45309" if self.theme_var.get() == "Light" else "#FBBF24"

            ctk.CTkLabel(warn, text="⚠ Expenses after next payday",
                        text_color=warn_color,
                        font=ctk.CTkFont(family="Verdana", size=12, weight="bold")).pack(anchor="w")

            for i, t in enumerate(after_bills[:3]):
                if i < 2:
                    txt = f"• {t['desc'][:18]}  ${t['expense']:,.0f}"
                    ctk.CTkLabel(warn, text=txt,
                                font=ctk.CTkFont(family="Verdana", size=12)).pack(anchor="w")
                else:
                    remaining = len(after_bills) - 3
                    line = ctk.CTkFrame(warn, fg_color="transparent")
                    line.pack(anchor="w")

                    ctk.CTkLabel(line, text=f"• {t['desc'][:18]}  ${t['expense']:,.0f}  ",
                                font=ctk.CTkFont(family="Verdana", size=12)).pack(side="left")

                    if remaining > 0:
                        more_label = ctk.CTkLabel(
                            line,
                            text=f"+ {remaining} more",
                            font=ctk.CTkFont(family="Verdana", size=12),
                            text_color="gray"
                        )
                        more_label.pack(side="left")

                        remaining_items = after_bills[3:]
                        tip_lines = [f"• {t['desc']}  ${t['expense']:,.0f}" for t in remaining_items]
                        WidgetTooltip(more_label, "Remaining expenses:\n" + "\n".join(tip_lines))

        # ========== MAIN CONTENT ==========
        content = ctk.CTkFrame(win, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(2, 0))

        table_frame = ctk.CTkFrame(content, corner_radius=10)
        table_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        cols = ("date", "desc", "category", "income", "expense", "balance", "paid")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=22)
        for c, h in zip(cols, ["Date", "Description", "Category", "Income", "Expense", "Running Bal", "Paid?"]):
            tree.heading(c, text=h)
            tree.column(c, width=105 if c != "desc" else 170, anchor="center")

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.proj_tree = tree

        if self.theme_var.get() == "Light":
            tree.tag_configure("paid", background="#c8c8c8", foreground="#555555")
            tree.tag_configure("highlight", background="#1f1f1f", foreground="#9cdcfe")
            tree.tag_configure("startbal", background="#F0F2F5", foreground="#1F2937")
        else:
            tree.tag_configure("paid", background="#2a2a2a", foreground="#999999")
            tree.tag_configure("highlight", background="#e7d743", foreground="#141414")
            tree.tag_configure("startbal", background="#1f1f1f", foreground="#ce9178")

        past_rows   = [t for t in tx if t["date"] < as_of]
        future_rows = [t for t in tx if t["date"] >= as_of]

        bal_dates = [as_of]
        bal_values = [start_bal]
        six_months = as_of + relativedelta(months=6)

        notes_map = {}

        for t in past_rows:
            if self.hide_paid and t["is_paid"]:
                continue
            paid_symbol = "☑" if t["is_paid"] else "☐"
            month_idx = t["date"].month - 1
            key = f"{t['date']}|{t['desc']}"
            notes_map[key] = t.get("notes", "")
            tags = [f"month{month_idx}", key]
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
            if self.hide_paid and t["is_paid"]:
                continue
            inc = t["income"] if not t["is_paid"] else 0.0
            exp = t["expense"] if not t["is_paid"] else 0.0
            balance += inc - exp
            if t["date"] <= six_months:
                bal_dates.append(t["date"])
                bal_values.append(balance)
            paid_symbol = "☑" if t["is_paid"] else "☐"
            month_idx = t["date"].month - 1
            key = f"{t['date']}|{t['desc']}"
            notes_map[key] = t.get("notes", "")
            tags = [f"month{month_idx}", key]
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

        def toggle_selection(event):
            item = tree.identify_row(event.y)
            if not item:
                return "break"
            current_selection = tree.selection()
            if item in current_selection:
                tree.selection_remove(item)
            else:
                tree.selection_set(item)
            return "break"

        tree.unbind("<Button-1>")
        tree.bind("<Button-1>", toggle_selection)

        def get_proj_note(item):
            tags = tree.item(item, "tags")
            if len(tags) >= 2:
                return notes_map.get(tags[1], "")
            return ""
        TreeviewTooltip(tree, get_proj_note)

        # RIGHT SIDE – TREEMAP
        chart_frame = ctk.CTkFrame(content, width=390, corner_radius=10)
        chart_frame.pack(side="right", fill="y")
        chart_frame.pack_propagate(False)

        ctk.CTkLabel(chart_frame, text="Next 30 Days – Expenses",
                    font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(pady=(8, 2))

        if cat_totals:
            full_sorted = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)

            set3 = list(plt.cm.Set3.colors)
            color_map = {cat: set3[i % len(set3)] for i, (cat, _) in enumerate(full_sorted)}
            color_map["Other"] = "#555555"

            if len(full_sorted) > 10:
                main_items = full_sorted[:9]
                other_total = sum(v for _, v in full_sorted[9:])
                treemap_items = main_items + [("Other", other_total)]
                other_categories = [cat for cat, _ in full_sorted[9:]]
            else:
                treemap_items = full_sorted
                other_categories = []

            values = [v for _, v in treemap_items]
            categories = [k for k, _ in treemap_items]
            colors = [color_map[cat] for cat in categories]

            fig, ax = plt.subplots(figsize=(5.0, 3.6), dpi=100)
            is_dark = self.theme_var.get() == "Dark"
            bg = "#2b2b2b" if is_dark else "white"
            legend_color = "#e0e0e0" if is_dark else "black"
            fig.patch.set_facecolor(bg)
            ax.set_facecolor(bg)

            patches, ordered_cats = self._draw_treemap(ax, categories, values, colors)

            legend_labels = [f"{cat}  ${val:,.0f}" for cat, val in treemap_items]
            legend = ax.legend(
                patches, legend_labels,
                loc="upper center", bbox_to_anchor=(0.5, -0.04),
                ncol=2, frameon=False, fontsize=10,
                handlelength=1.0, handletextpad=0.35, columnspacing=0.8, borderaxespad=0.05
            )
            for text in legend.get_texts():
                text.set_color(legend_color)

            fig.tight_layout()
            fig.subplots_adjust(bottom=0.40, top=0.95, left=0.02, right=0.98)

            treemap_canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            treemap_canvas.draw()
            treemap_canvas.get_tk_widget().configure(height=380)
            treemap_canvas.get_tk_widget().pack(pady=(2, 0), padx=4, fill="x")

            self._treemap_canvas = treemap_canvas
            self._treemap_fig = fig

            def on_treemap_click(event):
                if event.artist not in patches:
                    return
                idx = patches.index(event.artist)
                category = ordered_cats[idx]

                if category == "Other":
                    self._clear_category_highlight()
                    cutoff = getattr(self, "_treemap_cutoff", None)

                    for cat in other_categories:
                        for item in self.proj_tree.get_children():
                            vals = self.proj_tree.item(item, "values")
                            if len(vals) < 3 or vals[2] != cat:
                                continue

                            if cutoff is not None:
                                try:
                                    row_date = datetime.strptime(str(vals[0]), "%Y-%m-%d").date()
                                    if not (cutoff - timedelta(days=30) <= row_date <= cutoff):
                                        continue
                                except Exception:
                                    continue

                            tags = list(self.proj_tree.item(item, "tags"))
                            if "highlight" not in tags:
                                tags.append("highlight")
                            self.proj_tree.item(item, tags=tags)

                    self._highlighted_category = "Other"
                    self.status_label.configure(
                        text=f"Highlighted Other ({len(other_categories)} categories) – next 30 days",
                        text_color="#9ece6a"
                    )
                else:
                    if self._highlighted_category == category:
                        self._clear_category_highlight()
                    else:
                        self._highlight_category(category)

            treemap_canvas.mpl_connect("pick_event", on_treemap_click)

            # Hover tooltip for “Other”
            self._treemap_tip = None
            self._treemap_tip_label = None
            self._treemap_after_id = None

            def hide_treemap_tip():
                if self._treemap_after_id is not None:
                    try:
                        treemap_canvas.get_tk_widget().after_cancel(self._treemap_after_id)
                    except Exception:
                        pass
                    self._treemap_after_id = None
                if self._treemap_tip is not None:
                    try:
                        self._treemap_tip.withdraw()
                    except Exception:
                        pass

            def _actually_show(text, x, y):
                is_dark = self.theme_var.get() == "Dark"
                bg = "#1F2937" if is_dark else "#FFFFFF"
                fg = "#e0e0e0" if is_dark else "#1F2937"
                border_col = "#3B82F6"

                if self._treemap_tip is None:
                    self._treemap_tip = tw = ctk.CTkToplevel(treemap_canvas.get_tk_widget())
                    tw.wm_overrideredirect(True)
                    tw.attributes("-topmost", True)

                    border_frame = ctk.CTkFrame(tw, fg_color=border_col, corner_radius=3)
                    border_frame.pack()

                    inner = ctk.CTkFrame(border_frame, fg_color=bg, corner_radius=2)
                    inner.pack(padx=3, pady=3)

                    self._treemap_tip_label = ctk.CTkLabel(
                        inner, text=text, fg_color="transparent", text_color=fg,
                        font=ctk.CTkFont(family="Verdana", size=11),
                        justify="left", padx=10, pady=7
                    )
                    self._treemap_tip_label.pack()
                else:
                    self._treemap_tip_label.configure(text=text)

                self._treemap_tip.wm_geometry(f"+{x}+{y}")
                self._treemap_tip.deiconify()
                self._treemap_tip.lift()

            def show_treemap_tip(text):
                hide_treemap_tip()
                try:
                    x = treemap_canvas.get_tk_widget().winfo_pointerx() + 14
                    y = treemap_canvas.get_tk_widget().winfo_pointery() + 12
                except Exception:
                    return
                self._treemap_after_id = treemap_canvas.get_tk_widget().after(
                    40, lambda: _actually_show(text, x, y)
                )

            def on_hover(event):
                try:
                    if event.x is None or event.y is None:
                        hide_treemap_tip()
                        return
                    found = False
                    for i, patch in enumerate(patches):
                        hit = False
                        try:
                            hit, _ = patch.contains(event)
                        except Exception:
                            pass
                        if not hit:
                            try:
                                hit = patch.contains_point((event.x, event.y), radius=18)
                            except Exception:
                                pass
                        if hit and ordered_cats[i] == "Other" and other_categories:
                            lines = [f"• {c}  ${cat_totals.get(c, 0):,.0f}" for c in other_categories]
                            show_treemap_tip("Other contains:\n" + "\n".join(lines))
                            found = True
                            break
                    if not found:
                        hide_treemap_tip()
                except Exception:
                    hide_treemap_tip()

            treemap_canvas.mpl_connect("motion_notify_event", on_hover)
            treemap_canvas.get_tk_widget().bind("<Leave>", lambda e: hide_treemap_tip())

        else:
            ctk.CTkLabel(chart_frame, text="No expenses in next 30 days",
                         font=ctk.CTkFont(family="Verdana", size=12)).pack(pady=30)

        # THIS MONTH panel
        this_month = ctk.CTkFrame(chart_frame, corner_radius=8,
                                  border_width=1, border_color=("#d0d0d0", "#555555"))
        this_month.pack(fill="x", padx=8, pady=(8, 0))

        ctk.CTkLabel(this_month, text="This Month",
                     font=ctk.CTkFont(family="Verdana", size=13, weight="bold")).pack(pady=(4, 2))

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

        make_row(this_month, "Income:", "income")
        make_row(this_month, "Expenses:", "expense", "#C62828")
        make_row(this_month, "Net:", "net")
        make_row(this_month, "Still unpaid:", "unpaid", "#E65100")

        self._update_month_panel(month_labels[0])

        # ========== RUNNING BALANCE CHART ==========
        chart_bottom = ctk.CTkFrame(win, corner_radius=10, height=115)
        chart_bottom.pack(fill="x", padx=14, pady=(0, 8))
        chart_bottom.pack_propagate(False)

        if len(bal_dates) > 1:
            is_dark = self.theme_var.get() == "Dark"
            fig, ax = plt.subplots(figsize=(12, 1.45), dpi=100)
            fig.patch.set_facecolor("#2b2b2b" if is_dark else "#F0F2F5")
            ax.set_facecolor("#2b2b2b" if is_dark else "#F0F2F5")

            line, = ax.plot(bal_dates, bal_values, color="#3B82F6", linewidth=2.0)
            ax.fill_between(bal_dates, bal_values, alpha=0.18, color="#3B82F6")
            ax.grid(True, alpha=0.25)

            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
            ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
            ax.tick_params(axis='y', colors="#e0e0e0" if is_dark else "#1F2937", labelsize=8)

            for spine in ax.spines.values():
                spine.set_color("#555555" if is_dark else "#D1D5DB")

            ax.set_title("Running Balance (next 6 months)", fontsize=10,
                         color="#e0e0e0" if is_dark else "#1F2937", pad=2)

            fig.tight_layout(pad=0.2)
            fig.subplots_adjust(bottom=0.08, top=0.78, left=0.07, right=0.98)

            annot = ax.annotate(
                "", xy=(0, 0),
                xytext=(0, 20), textcoords="offset points",
                ha="center",
                bbox=dict(boxstyle="round,pad=0.35",
                          fc="#1F2937" if is_dark else "#FFFFFF",
                          ec="#3B82F6", lw=1.5, alpha=0.95),
                color="#e0e0e0" if is_dark else "#1F2937",
                fontsize=10, fontfamily="Verdana",
                arrowprops=dict(
                    arrowstyle="-",
                    color="#3B82F6",
                    lw=1.6,
                    connectionstyle="arc3,rad=0"
                ),
                clip_on=False,
                zorder=100
            )
            annot.set_visible(False)

            dates_num = mdates.date2num(bal_dates)

            def hover(event, canvas=None):
                if event.inaxes != ax or event.xdata is None:
                    if annot.get_visible():
                        annot.set_visible(False)
                        if canvas is not None:
                            canvas.draw_idle()
                    return

                x_num = event.xdata
                idx = min(range(len(dates_num)), key=lambda i: abs(dates_num[i] - x_num))

                if abs(dates_num[idx] - x_num) > 5:
                    if annot.get_visible():
                        annot.set_visible(False)
                        if canvas is not None:
                            canvas.draw_idle()
                    return

                x = bal_dates[idx]
                y = bal_values[idx]

                ylim = ax.get_ylim()
                y_range = ylim[1] - ylim[0]

                if (y - ylim[0]) / y_range > 0.55:
                    offset = -13
                    va = "top"
                else:
                    offset = 13
                    va = "bottom"

                annot.xy = (x, y)
                annot.set_position((0, offset))
                annot.set_va(va)
                annot.set_text(f"{x.strftime('%Y-%m-%d')}\n${y:,.2f}")
                annot.set_visible(True)

                if canvas is not None:
                    canvas.draw_idle()

            line_canvas = FigureCanvasTkAgg(fig, master=chart_bottom)
            line_canvas.draw()
            line_canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=3)

            self._proj_canvas = line_canvas
            self._proj_fig = fig

            line_canvas.mpl_connect("motion_notify_event",
                                    lambda e: hover(e, canvas=line_canvas))
                        
        else:
            ctk.CTkLabel(chart_bottom, text="Running balance chart (need more data)",
                         font=ctk.CTkFont(family="Verdana", size=12), text_color="gray").pack(expand=True)

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

        income_color = "#2E7D32" if self.theme_var.get() == "Light" else "#9ece6a"
        net_color = income_color if net >= 0 else "#C62828"

        labels["income"].configure(text=f"${income:,.2f}", text_color=income_color)
        labels["expense"].configure(text=f"${expense:,.2f}")
        labels["unpaid"].configure(text=f"${unpaid:,.2f}")
        labels["net"].configure(text=f"${net:,.2f}", text_color=net_color)

# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    last = load_last_budget()
    if last:
        if not acquire_lock(last):
            root = ctk.CTk()
            root.withdraw()
            messagebox.showerror(
                "Budget already open",
                f"The budget file “{last}” is already open in another window.\n\n"
                "Please close the other instance first."
            )
            root.destroy()
            sys.exit(0)

        CURRENT_DB = last
        app = BudgetApp()
        app.mainloop()
    else:
        launcher = BudgetLauncher()
        launcher.mainloop()
