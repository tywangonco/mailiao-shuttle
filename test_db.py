from app import init_db, add_available_date, get_available_dates, add_reservation, get_reservations, DB_FILE
import sqlite3
import os

# Clean up before start
if os.path.exists(DB_FILE):
    try:
        os.remove(DB_FILE)
    except:
        pass

print("1. Initializing DB...")
init_db()

print("2. Checking default dates...")
dates = get_available_dates()
print(f"Dates: {dates}")
assert '2026-03-05' in dates
assert '2026-03-10' in dates

print("3. Adding new date...")
add_available_date('2026-04-01')
dates = get_available_dates()
print(f"Dates after add: {dates}")
assert '2026-04-01' in dates

print("4. Adding reservation...")
success, msg = add_reservation('2026-04-01', 'MRN123', 'Test Patient', '0900000000', 0)
print(f"Add Reservation: {success}, {msg}")
assert success == True

print("5. Checking reservation...")
df = get_reservations('2026-04-01')
print(df)
assert len(df) == 1
assert df.iloc[0]['patient_name'] == 'Test Patient'

print("ALL TESTS PASSED")
