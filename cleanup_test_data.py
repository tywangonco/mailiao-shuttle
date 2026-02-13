from app import remove_available_date, get_available_dates
import sqlite3

# Clean up test data
print("Current dates:", get_available_dates())

# Remove 2026-04-01
target_date = '2026-04-01'
if target_date in get_available_dates():
    success, msg = remove_available_date(target_date)
    print(msg)
else:
    print(f"Date {target_date} not found (might have been removed).")

print("Final dates:", get_available_dates())
assert '2026-04-01' not in get_available_dates()
