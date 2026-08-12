# Personal Budget Tracker (v0.93)

A clean, modern desktop budget tracker built with Python + CustomTkinter.

Track multiple budgets, expenses, and incomes with a clear financial projection, Safe-to-Spend calculations, interactive charts, and paid/unpaid tracking — all in a single window.

---

## What's New in v0.93

- **Projection is now a top-level tab** (no more separate window)
- Top bar with **Budget | Projection** switcher + Theme picker on the same row
- Main income (★) can be set on **any** income type
- Hourly Main income correctly uses rate × hours
- Click treemap **blocks or legend items** to highlight matching rows
- Switching budgets returns you to the Budget tab cleanly
- More reliable projection rebuilds (End Date, Paid, Hide paid, etc.)
- Many small polish and stability improvements

---

## Features

- Multiple independent budget files (`.db`) with recent list + Browse / Create New
- Save budgets anywhere on your computer (not locked next to the exe)
- Expenses & Incomes with flexible frequencies  
  (Weekly → Bi-weekly → Monthly → Quarterly → Annual / One-time)
- Main income (star) support for any income type
- Safe-to-Spend calculator with customizable end date
- Projection tab with:
  - Full transaction list + Running Balance chart
  - Double-click to toggle Paid / Unpaid
  - Interactive Squarified Treemap (Next 30 Days)
  - Click treemap blocks **or legend** to highlight matching rows
  - “This Month” summary panel
- Quick Overview dashboard (Account Snapshot)
- Light / Dark themes (remembers your preference)
- Drag-and-drop reordering
- Column width memory
- Prevents opening the same budget in two windows
- Application icon included

---

## Option 1 – Download the ready-to-run version (Recommended)

1. Go to the [Releases](../../releases) page
2. Download the latest `.exe` (Windows) or `.zip` / `.app` (macOS if available)
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
