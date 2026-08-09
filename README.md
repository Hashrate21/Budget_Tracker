# Personal Budget Tracker (Beta)

A clean desktop budget tracker built with Python + CustomTkinter.

## Features
- Multiple budget files (mybudget.db, yourbudget.db, etc.)
- Bills & Incomes with flexible frequencies
- Safe-to-Spend calculator (Strict / Inclusive + Next Pay / End of Month)
- Projection window with running balance + 30-day expense pie chart
- Light / Dark theme
- Remembers column widths
- Application icon included

---

## Option 1 – Download the ready-to-run version (Recommended)

1. Go to the [Releases](../../releases) page
2. Download `PersonalBudgetTracker.exe`
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
