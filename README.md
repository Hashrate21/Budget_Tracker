# Personal Budget Tracker (v0.90)

A clean, modern desktop budget tracker built with Python + CustomTkinter.

Track multiple budgets, expenses, incomes, and see a clear projection of your finances with Safe-to-Spend calculations, interactive charts, and paid/unpaid tracking.

---

## What's New in v0.90

- Completely redesigned Projection header (responsive grid)
- New Year / Month / Day dropdown End Date picker
- Pie chart replaced with a space-efficient **Squarified Treemap**
- Improved Running Balance chart (cleaner axes + better hover tooltips)
- “Other” category in the treemap now has a detailed hover tooltip
- Tips & Shortcuts window (wider, better aligned, easy to extend)
- Many small UI and reliability improvements
- Fixed calendar popup closing when clicking month/year headers

---

## Features

- Multiple independent budget files (`.db`)
- Expenses & Incomes with flexible frequencies  
  (Monthly, Bi-weekly, Weekly, Quarterly, Annual, One-time)
- Main income (star) support
- Safe-to-Spend calculator with customizable end date
- Projection window with:
  - Full transaction list + Running Balance
  - Double-click to toggle Paid / Unpaid
  - Interactive Squarified Treemap (Next 30 Days)
  - “This Month” summary panel
  - Click treemap blocks to highlight matching rows
- Quick Overview dashboard on the main window
- Light / Dark themes
- Drag-and-drop reordering
- Column width memory
- Application icon included

---

## Option 1 – Download the ready-to-run version (Recommended)

1. Go to the [Releases](../../releases) page
2. Download the latest `.exe`
3. Double-click it — no Python installation needed

> Windows may show a SmartScreen warning the first time (normal for new unsigned apps).  
> Click **More info** → **Run anyway**.

---

## Option 2 – Run from source

### Requirements
- Python 3.10 or newer

### Steps
```bash
pip install -r requirements.txt
python Budget_Tracker.py
