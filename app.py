import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime

# --- Configuration ---
SHEET_NAME = "shuttle_db"
WORKSHEET_RESERVATIONS = "reservations"
WORKSHEET_DATES = "allowed_dates"

PATIENT_LIMIT = 4
SEAT_LIMIT = 6  # Total seats excluding driver

# --- Google Sheets Connection ---
def init_connection():
    """
    Establish connection to Google Sheets using Service Account from st.secrets.
    """
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    if "gcp_service_account" not in st.secrets:
        st.error("❌ 未設定 GCP Service Account，請在 secrets.toml 中設定 [gcp_service_account]。")
        st.stop()
        
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_worksheet(client, worksheet_name):
    try:
        sheet = client.open(SHEET_NAME)
        return sheet.worksheet(worksheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ 找不到試算表: {SHEET_NAME}。請確認已建立並分享給 Service Account。")
        st.stop()
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ 找不到分頁: {worksheet_name}。請確認分頁名稱正確。")
        st.stop()

# --- Data Operations ---
def get_data(client):
    """Fetch all data from both sheets."""
    try:
        res_sheet = get_worksheet(client, WORKSHEET_RESERVATIONS)
        dates_sheet = get_worksheet(client, WORKSHEET_DATES)
        
        res_data = res_sheet.get_all_records()
        dates_data = dates_sheet.get_all_records()
        
        res_df = pd.DataFrame(res_data)
        dates_df = pd.DataFrame(dates_data)
        
        # Ensure correct types for filtering if empty
        if 'date' not in dates_df.columns:
            dates_df['date'] = []
            
        return res_df, dates_df
    except Exception as e:
        st.error(f"讀取資料失敗: {e}")
        return pd.DataFrame(), pd.DataFrame()

def add_reservation(client, reserve_date, mrn, name, phone, family_count):
    """Add a reservation with capacity checks."""
    res_sheet = get_worksheet(client, WORKSHEET_RESERVATIONS)
    res_data = res_sheet.get_all_records()
    df = pd.DataFrame(res_data)
    
    # Check if duplicate (MRN + Date)
    if not df.empty:
        # Normalize date to string for comparison
        reserve_date_str = str(reserve_date)
        # Check duplicate
        duplicate = df[(df['date'].astype(str) == reserve_date_str) & (df['mrn'].astype(str) == str(mrn))]
        if not duplicate.empty:
            return False, "該病患當日已預約，請勿重複預約。"
        
        # Filter for logic
        day_reservations = df[df['date'].astype(str) == reserve_date_str]
        
        # Capacity Rule 1: Max 4 patients
        current_patients = len(day_reservations)
        if current_patients >= PATIENT_LIMIT:
            return False, f"預約失敗：當日病患名額已滿 ({PATIENT_LIMIT}人)。"

        # Capacity Rule 2: Max 6 total seats
        current_family = day_reservations['family_count'].sum() if 'family_count' in day_reservations.columns else 0
        total_people = current_patients + current_family
        needed_seats = 1 + family_count
        
        if total_people + needed_seats > SEAT_LIMIT:
             return False, f"預約失敗：剩餘座位不足 (剩餘 {SEAT_LIMIT - total_people} 席)。"
    
    # Append to sheet
    new_row = [
        str(reserve_date),
        str(mrn),
        name,
        str(phone),
        family_count,
        str(datetime.now())
    ]
    res_sheet.append_row(new_row)
    return True, "預約成功！"

def cancel_reservation(client, mrn, phone):
    """Cancel reservation by MRN and Phone."""
    res_sheet = get_worksheet(client, WORKSHEET_RESERVATIONS)
    # Finding the row to delete is tricky without unique ID.
    # We will fetch all, find the index, then delete row (index + 2 because 1-based + 1-header)
    all_values = res_sheet.get_all_values()
    
    # Skip header
    header = all_values[0]
    data = all_values[1:]
    
    # Assuming columns: date, mrn, name, phone...
    # Find matching row index
    row_to_delete = -1
    for i, row in enumerate(data):
        # row indices: 1=mrn, 3=phone (based on append order)
        # Verify column order from your sheet or code assumption
        # My append order: date, mrn, name, phone
        r_mrn = row[1]
        r_phone = row[3]
        
        if str(r_mrn) == str(mrn) and str(r_phone) == str(phone):
            row_to_delete = i + 2 # +2 for header and 0-index offset
            break
            
    if row_to_delete != -1:
        res_sheet.delete_rows(row_to_delete)
        return True, "已取消預約。"
    else:
        return False, "找不到對應的預約記錄。"

def add_allowed_date(client, date_str):
    """Add a date to allowed_dates."""
    dates_sheet = get_worksheet(client, WORKSHEET_DATES)
    # Check exists
    dates = dates_sheet.col_values(1) # Column A
    if date_str in dates:
        return False, "日期已存在。"
    
    dates_sheet.append_row([date_str])
    return True, f"已新增日期: {date_str}"

def remove_allowed_date(client, date_str):
    """Remove a date from allowed_dates."""
    dates_sheet = get_worksheet(client, WORKSHEET_DATES)
    cell = dates_sheet.find(date_str)
    if cell:
        dates_sheet.delete_rows(cell.row)
        return True, f"已刪除日期: {date_str}"
    else:
        return False, "找不到該日期。"

# --- Main App ---
def main():
    st.set_page_config(page_title="麥寮CT專車預約 (GSheets版)", page_icon="🚑")
    st.title("🚑 麥寮CT專車預約系統")

    # Connect to GSheets
    try:
        client = init_connection()
    except Exception as e:
        st.error(f"連線失敗: {e}")
        st.stop()

    # --- Sidebar: Admin ---
    st.sidebar.header("👮 管理員後台")
    
    if "ADMIN_PASSWORD" not in st.secrets:
        st.error("請設定 secrets.toml 中的 [ADMIN_PASSWORD]")
        st.stop()

    admin_password = st.sidebar.text_input("請輸入管理員密碼", type="password")

    if admin_password == st.secrets["ADMIN_PASSWORD"]:
        st.sidebar.success("已登入")
        
        # Load Data
        res_df, dates_df = get_data(client)
        
        st.sidebar.subheader("📅 開放日期管理")
        
        # Show Current Dates
        if not dates_df.empty:
            dates_list = dates_df['date'].astype(str).tolist()
            dates_list.sort()
        else:
            dates_list = []
            
        # Add Date
        with st.sidebar.expander("➕ 新增日期"):
            new_date = st.date_input("選擇日期", min_value=date.today())
            if st.button("新增"):
                success, msg = add_allowed_date(client, str(new_date))
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

        # Remove Date
        with st.sidebar.expander("🗑️ 移除日期"):
            if dates_list:
                rm_date = st.selectbox("選擇移除日期", dates_list)
                if st.button("移除"):
                    success, msg = remove_allowed_date(client, rm_date)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.info("無開放日期")

        st.sidebar.markdown("---")
        st.sidebar.subheader("📋 預約總覽")
        if st.sidebar.checkbox("顯示所有預約資料"):
            st.sidebar.dataframe(res_df)

    elif admin_password:
        st.sidebar.error("密碼錯誤")

    # --- Main Area ---
    tab1, tab2 = st.tabs(["📅 預約登記", "❌ 取消預約"])

    # Load fresh data for user
    res_df, dates_df = get_data(client)
    
    # Prepare valid dates
    if not dates_df.empty and 'date' in dates_df.columns:
        valid_dates = sorted(dates_df['date'].astype(str).unique())
        # Filter past dates
        today_str = str(date.today())
        valid_dates = [d for d in valid_dates if d >= today_str]
    else:
        valid_dates = []

    with tab1:
        st.header("新增預約")
        if not valid_dates:
            st.warning("⚠️ 目前沒有開放可預約的日期。")
        else:
            with st.form("booking_form"):
                col1, col2 = st.columns(2)
                with col1:
                    reserve_date = st.selectbox("選擇日期", valid_dates)
                    mrn = st.text_input("病歷號 (MRN)")
                    patient_name = st.text_input("病人姓名")
                with col2:
                    phone = st.text_input("聯絡電話")
                    family_count = st.selectbox("陪同家屬人數", [0, 1])
                
                submitted = st.form_submit_button("送出預約")
                
                if submitted:
                    if not mrn or not phone or not patient_name:
                        st.error("請填寫所有欄位。")
                    else:
                        success, msg = add_reservation(client, reserve_date, mrn, patient_name, phone, family_count)
                        if success:
                            st.success(msg)
                            # Optional: st.rerun() to refresh capacity view
                        else:
                            st.error(msg)
            
            # Show Capacity for selected date
            if reserve_date and not res_df.empty and 'date' in res_df.columns:
                day_df = res_df[res_df['date'].astype(str) == str(reserve_date)]
                p_count = len(day_df)
                f_count = day_df['family_count'].sum() if 'family_count' in day_df.columns else 0
                st.info(f"ℹ️ {reserve_date} 預約狀況: 病患 {p_count}/{PATIENT_LIMIT}, 總人數 {p_count+f_count}/{SEAT_LIMIT}")

    with tab2:
        st.header("取消預約")
        with st.form("cancel_form"):
            c_mrn = st.text_input("病歷號 (MRN)")
            c_phone = st.text_input("聯絡電話")
            confirm = st.form_submit_button("確認取消")
            
            if confirm:
                if c_mrn and c_phone:
                    success, msg = cancel_reservation(client, c_mrn, c_phone)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.error("請輸入完整資訊。")

if __name__ == "__main__":
    main()
