# Personal Budget Tracker (v0.91)

A clean, modern desktop budget tracker built with Python + CustomTkinter.

Track multiple budgets, expenses, and incomes with a clear financial projection, Safe-to-Spend calculations, interactive charts, and paid/unpaid tracking.

---

## What's New in v0.91

- **Theme is now remembered** between sessions
- Renamed “Current Inputs” → **Account Snapshot**
- Added helpful tooltips (Safe to Spend, “+ more” expenses, etc.)
- Improved tooltip styling with consistent borders
- Weekly frequency added to Expenses
- Frequency dropdowns ordered from shortest to longest period
- Debounced expense search for smoother filtering
- Better tab bar styling and rounded corners
- Guard against opening the same budget file twice
- Many small UI polish and reliability improvements

---

## Features

- Multiple independent budget files (`.db`)
- Expenses & Incomes with flexible frequencies  
  (Weekly → Bi-weekly → Monthly → Quarterly → Annual / One-time)
- Main income (star) support
- Safe-to-Spend calculator with customizable end date
- Projection window with:
  - Full transaction list + Running Balance chart
  - Double-click to toggle Paid / Unpaid
  - Interactive Squarified Treemap (Next 30 Days)
  - “This Month” summary panel
  - Click treemap blocks to highlight matching rows
- Quick Overview dashboard
- Light / Dark themes (remembers your preference)
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
