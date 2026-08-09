# Personal Budget Tracker (Beta v0.8)

A clean desktop budget tracker built with Python + CustomTkinter.

## What's New in v0.8
- **This Month** panel (Income / Expenses / Net / Still unpaid)
- Managed Category dropdown + Manage Categories dialog
- Projection table now shows earlier bills in the current month (you can mark them paid/unpaid)
- Safe-to-Spend includes primary paycheck when using “Until End of Month”
- Full bill amounts are always shown (even when marked as paid)
- Improved current-month calculations

## Features
- Multiple budget files (`.db` files)
- Bills & Incomes with flexible frequencies (Monthly, Bi-weekly, Quarterly, Annual, Weekly, etc.)
- Primary Paycheck support (Days Interval + Semi-monthly options)
- Safe-to-Spend calculator  
  - Period: Until Next Pay / Until End of Month  
  - Mode: Strict / Inclusive
- Projection window with:
  - Running balance
  - Paid/Unpaid toggle (double-click)
  - 30-day expense pie chart
  - This Month summary
- Light / Dark theme
- Remembers column widths
- Application icon included

---

## Option 1 – Download the ready-to-run version (Recommended)

1. Go to the [Releases](../../releases) page
2. Download `PersonalBudgetTracker_v0.8-beta.exe`
3. Double-click it — no Python or installation needed

> Windows may show a SmartScreen warning the first time (normal for new apps).  
> Click **More info** → **Run anyway**.

---

## Option 2 – Run from source

### Requirements
- Python 3.10 or newer

### Steps
```bash
pip install -r requirements.txt
python budget_tracker.py