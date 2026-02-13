import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date

# --- Configuration ---
DB_FILE = 'shuttle.db'
patient_limit = 4
seat_limit = 6  # Total seats excluding driver

# --- Database Functions ---
def init_db():
    """Initialize the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Reservations Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reserve_date TEXT NOT NULL,
            mrn TEXT NOT NULL,
            patient_name TEXT,
            phone TEXT NOT NULL,
            family_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if patient_name column exists (migration)
    c.execute("PRAGMA table_info(reservations)")
    columns = [info[1] for info in c.fetchall()]
    if 'patient_name' not in columns:
        c.execute("ALTER TABLE reservations ADD COLUMN patient_name TEXT")

    # 2. Available Dates Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS available_dates (
            date_value TEXT PRIMARY KEY
        )
    ''')

    # Initialize default dates if empty
    c.execute("SELECT count(*) FROM available_dates")
    if c.fetchone()[0] == 0:
        default_dates = ['2026-03-05', '2026-03-10']
        for d in default_dates:
            c.execute("INSERT OR IGNORE INTO available_dates (date_value) VALUES (?)", (d,))

    conn.commit()
    conn.close()

def get_available_dates():
    """Get list of available dates (sorted)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date_value FROM available_dates ORDER BY date_value")
    dates = [row[0] for row in c.fetchall()]
    conn.close()
    return dates

def add_available_date(date_str):
    """Add a single available date."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO available_dates (date_value) VALUES (?)", (date_str,))
        conn.commit()
        success = True
        msg = f"已新增日期: {date_str}"
    except sqlite3.IntegrityError:
        success = False
        msg = f"日期 {date_str} 已存在。"
    finally:
        conn.close()
    return success, msg

def remove_available_date(date_str):
    """Remove a date from available list."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM available_dates WHERE date_value = ?", (date_str,))
    conn.commit()
    conn.close()
    return True, f"已移除日期: {date_str}"

def get_reservations(reserve_date):
    """Fetch reservations for a specific date."""
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT * FROM reservations WHERE reserve_date = ?"
    df = pd.read_sql_query(query, conn, params=(str(reserve_date),))
    conn.close()
    return df

def add_reservation(reserve_date, mrn, patient_name, phone, family_count):
    """Try to add a reservation. Returns (Success, Message)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check constraints
    # 1. Check if patient already booked (optional but good practice)
    c.execute("SELECT * FROM reservations WHERE reserve_date = ? AND mrn = ?", (str(reserve_date), mrn))
    if c.fetchone():
        conn.close()
        return False, "該病患當日已預約，請勿重複預約。"

    # Get current stats
    df = get_reservations(reserve_date)
    current_patients = len(df)
    current_people = len(df) + df['family_count'].sum() if not df.empty else 0
    
    # Core Logic Constraints
    # Rule 1: Max 4 patients
    if current_patients >= patient_limit:
        conn.close()
        return False, f"預約失敗：當日病患名額已滿 ({patient_limit}人)。"
    
    # Rule 2: Max 6 total seats
    needed_seats = 1 + family_count # Patient + Family
    if current_people + needed_seats > seat_limit:
        conn.close()
        return False, f"預約失敗：剩餘座位不足 (剩餘 {seat_limit - current_people} 席，需要 {needed_seats} 席)。"

    # Insert
    c.execute('''
        INSERT INTO reservations (reserve_date, mrn, patient_name, phone, family_count)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(reserve_date), mrn, patient_name, phone, family_count))
    conn.commit()
    conn.close()
    return True, "預約成功！"

def cancel_reservation(mrn, phone):
    """Cancel a reservation. Returns (Success, Message)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("DELETE FROM reservations WHERE mrn = ? AND phone = ?", (mrn, phone))
    rows_deleted = c.rowcount
    conn.commit()
    conn.close()
    
    if rows_deleted > 0:
        return True, f"已取消 MRN: {mrn} 的預約。"
    else:
        return False, "找不到對應的預約記錄 (請檢查病歷號與電話)。"

# --- Main App ---
# --- Main App ---
def main():
    st.set_page_config(page_title="麥寮CT專車預約系統", page_icon="🚑")
    init_db()

    st.title("🚑 麥寮CT專車預約系統")
    
    # --- Sidebar: Admin View ---
    st.sidebar.header("👮 管理員後台")
    
    # 1. View Reservations
    st.sidebar.subheader("📋 預約清單檢視")
    admin_date = st.sidebar.date_input("選擇日期查看清單", date.today())
    
    if st.sidebar.checkbox("顯示當日清單", value=True):
        df = get_reservations(admin_date)
        if not df.empty:
            st.sidebar.write(f"**{admin_date} 隨車人員清單**")
            # Display readable columns
            display_df = df[['mrn', 'patient_name', 'family_count', 'phone']].copy()
            display_df.columns = ['病歷號', '姓名', '家屬', '電話']
            st.sidebar.dataframe(display_df, hide_index=True)
            
            # Stats
            total_patients = len(df)
            total_family = df['family_count'].sum()
            total_people = total_patients + total_family
            
            st.sidebar.info(f"""
            📊 統計資訊：
            - 病患人數：{total_patients} / {patient_limit}
            - 總佔座位：{total_people} / {seat_limit}
            - 剩餘座位：{seat_limit - total_people}
            """)
        else:
            st.sidebar.warning("該日期尚無預約。")

    # 2. Date Management
    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 開放日期管理")
    
    with st.sidebar.expander("➕ 新增開放日期"):
        # Single Date
        st.caption("新增單一日期")
        new_date = st.date_input("選擇日期", min_value=date.today(), key="new_date_single")
        if st.button("新增此日期"):
            success, msg = add_available_date(str(new_date))
            if success: st.success(msg)
            else: st.warning(msg)
            
        st.markdown("---")
        # Batch by Weekday
        st.caption("批次新增 (按星期)")
        col_s, col_e = st.sidebar.columns(2)
        start_d = col_s.date_input("起", value=date.today(), key="batch_start")
        end_d = col_e.date_input("迄", value=date.today() + pd.Timedelta(days=30), key="batch_end")
        
        weekdays = {0:'一', 1:'二', 2:'三', 3:'四', 4:'五', 5:'六', 6:'日'}
        target_weekday = st.selectbox("選擇星期", options=list(weekdays.keys()), format_func=lambda x: weekdays[x])
        
        if st.button("批次新增日期"):
            if start_d > end_d:
                st.error("日期範圍錯誤")
            else:
                count = 0
                curr = start_d
                while curr <= end_d:
                    if curr.weekday() == target_weekday:
                        s, _ = add_available_date(str(curr))
                        if s: count += 1
                    curr += pd.Timedelta(days=1)
                st.success(f"已新增 {count} 個可預約日期！")

    with st.sidebar.expander("🗑️ 移除開放日期"):
        st.caption("移除已開放的日期")
        removable_dates = get_available_dates()
        if removable_dates:
            date_to_remove = st.selectbox("選擇要移除的日期", removable_dates, key="remove_date_select")
            if st.button("確認移除"):
                success, msg = remove_available_date(date_to_remove)
                if success:
                    st.success(msg)
                    st.rerun() # Refresh to update lists
                else:
                    st.error(msg)
        else:
            st.info("目前無開放日期。")

    # --- Main Area ---
    tab1, tab2 = st.tabs(["📅 預約登記 (Register)", "❌ 取消預約 (Cancel)"])

    with tab1:
        st.header("新增預約")
        
        # Get available dates
        available_dates = get_available_dates()
        # Filter out past dates just in case
        today_str = str(date.today())
        valid_dates = [d for d in available_dates if d >= today_str]
        
        if not valid_dates:
            st.error("⚠️ 目前沒有開放可預約的日期，請聯繫管理員。")
        else:
            with st.form("booking_form"):
                col1, col2 = st.columns(2)
                with col1:
                    reserve_date = st.selectbox("選擇搭乘日期", valid_dates)
                    mrn = st.text_input("病歷號 (MRN)")
                    patient_name = st.text_input("病人姓名")
                with col2:
                    phone = st.text_input("聯絡電話")
                    family_count = st.selectbox("陪同家屬人數", [0, 1], help="每位病人最多攜帶 1 位家屬")
                
                submitted = st.form_submit_button("送出預約")
                
                if submitted:
                    if not mrn or not phone or not patient_name:
                        st.error("請填寫所有必填欄位 (病歷號、姓名、電話)。")
                    else:
                        success, msg = add_reservation(reserve_date, mrn, patient_name, phone, family_count)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
            
            # Show availability preview for selected date
            if reserve_date:
                df = get_reservations(reserve_date)
                p_count = len(df)
                seat_count = p_count + (df['family_count'].sum() if not df.empty else 0)
                st.info(f"ℹ️ {reserve_date} 預約狀況: 病患 {p_count}/{patient_limit}, 座位 {seat_count}/{seat_limit}")

    with tab2:
        st.header("取消預約")
        with st.form("cancel_form"):
            st.write("請輸入資料以驗證身份並取消預約。")
            c_mrn = st.text_input("病歷號 (MRN)")
            c_phone = st.text_input("聯絡電話")
            
            cancel_submitted = st.form_submit_button("確認取消")
            
            if cancel_submitted:
                if not c_mrn or not c_phone:
                    st.error("請輸入病歷號與電話。")
                else:
                    success, msg = cancel_reservation(c_mrn, c_phone)
                    if success:
                        st.success(msg)
                    else:
                        st.warning(msg)

if __name__ == "__main__":
    main()
