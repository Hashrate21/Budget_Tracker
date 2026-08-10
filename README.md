# Personal Budget Tracker (Beta v0.84)

A clean and modern desktop budget tracker built with Python + CustomTkinter.

## What's New in v0.84
- Beautiful **Cool Gray Light theme** (much easier on the eyes)
- Improved Dark theme pie chart (matches app frames)
- Larger, more readable pie chart legend
- **Quick Overview** dashboard on the main window (mini Safe-to-Spend + next 3 bills)
- Paid rows now turn grey when marked as paid
- Click any coloured month row to jump to that month in “This Month”
- Safe-to-Spend Period & Mode are now remembered
- New Actions menu: “Mark all past as paid” / “Clear all paid flags”
- Negative amounts allowed (with confirmation warning)
- Better date validation on all date fields
- Income reorder (Up / Down buttons)
- Many small UI polish improvements

## Features
- Multiple budget files (`.db` files)
- Bills & Incomes with flexible frequencies (Monthly, Bi-weekly, Quarterly, Annual, Weekly, etc.)
- Primary Paycheck support (Days Interval + 3 Semi-monthly options)
- Safe-to-Spend calculator  
  - Period: Until Next Pay / Until End of Month (1st of next month)  
  - Mode: Strict / Inclusive
- Projection window with:
  - Running balance
  - Paid/Unpaid toggle (double-click) – rows turn grey when paid
  - 30-day expense pie chart (theme-aware)
  - This Month summary with 12-month dropdown
- Quick Overview dashboard
- Light (Cool Gray) / Dark theme
- Remembers column widths and Safe-to-Spend settings
- Application icon included

---

## Option 1 – Download the ready-to-run version (Recommended)

1. Go to the [Releases](../../releases) page
2. Download `PersonalBudgetTracker_v0.84-beta.exe`
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
