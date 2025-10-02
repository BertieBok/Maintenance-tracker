import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
from io import BytesIO
import base64
import sys
import os

# -----------------------------------------------------------------------------
# Helper to locate data files when running as a PyInstaller one-file bundle
def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller onefile.
    """
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)
# -----------------------------------------------------------------------------

# --- Page config ---
st.set_page_config(page_title="Equipment Maintenance Tracker", layout="wide")

# --- Constants ---
FILE = resource_path("Processing Tracker.xlsx")
HISTORY_SHEET = "Service History"

# --- Logo helpers (responsive) ---
def _logo_mime_and_b64():
    data = st.session_state.get("logo_bytes")
    if not data:
        return None, None
    bts = data if isinstance(data, (bytes, bytearray)) else data.read()
    if isinstance(bts, (bytes, bytearray)):
        if bts[:4] == b'\x89PNG':
            mime = "image/png"
        elif bts[:2] == b'\xff\xd8':
            mime = "image/jpeg"
        else:
            mime = "image/png"
    else:
        mime = "image/png"
    b64 = base64.b64encode(bts).decode()
    return mime, b64

def show_responsive_logo(main=True):
    mime, b64 = _logo_mime_and_b64()
    if not b64:
        return
    css = """
    <style>
    .resp-logo-main { display:block; margin-bottom:8px; height:auto; }
    .resp-logo-side { display:block; margin-bottom:8px; height:auto; }
    @media (min-width:1400px) { .resp-logo-main { width:420px; } }
    @media (min-width:1100px) and (max-width:1399px) { .resp-logo-main { width:360px; } }
    @media (min-width:800px) and (max-width:1099px) { .resp-logo-main { width:280px; } }
    @media (max-width:799px) { .resp-logo-main { width:180px; } }
    @media (min-width:1100px) { .resp-logo-side { width:200px; } }
    @media (max-width:1099px) { .resp-logo-side { width:160px; } }
    </style>
    """
    cls = "resp-logo-main" if main else "resp-logo-side"
    html = f'{css}<img class="{cls}" src="data:{mime};base64,{b64}" alt="Company logo"/>'
    st.markdown(html, unsafe_allow_html=True)

# --- Session state defaults ---
if "logo_bytes" not in st.session_state:
    st.session_state.logo_bytes = None
if "auth" not in st.session_state:
    st.session_state.auth = False
if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = None
if "view_tag" not in st.session_state:
    st.session_state.view_tag = None
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "home"
if "main_sheet_name" not in st.session_state:
    st.session_state.main_sheet_name = None
if "editing_tag" not in st.session_state:
    st.session_state.editing_tag = None

# --- Demo credentials (replace in production) ---
SALT = "change_this_salt_for_prod_!@#"
USERS = {
    "supervisor": {
        "hash": hashlib.sha256((SALT + "supervisor123").encode()).hexdigest(),
        "role": "Supervisor"
    },
    "technician": {
        "hash": hashlib.sha256((SALT + "tech123").encode()).hexdigest(),
        "role": "Technician"
    }
}

# --- Data loading helpers ---
@st.cache_data(show_spinner=False)
def load_data():
    df_main = pd.read_excel(FILE, sheet_name=None, engine="openpyxl")
    main_sheet_name = list(df_main.keys())[0]
    df = df_main[main_sheet_name].copy()
    df.columns = df.columns.str.strip()
    history = df_main.get(
        HISTORY_SHEET,
        pd.DataFrame(columns=["Tag", "Serviced Date", "Interval (days)", "Service Type", "Logged At"])
    )
    return df, history, main_sheet_name

def save_data(df, history, main_sheet_name):
    with pd.ExcelWriter(FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df.to_excel(writer, index=False, sheet_name=main_sheet_name)
        history.to_excel(writer, index=False, sheet_name=HISTORY_SHEET)

# --- Load data early so sidebar can compute counts/options ---
df, history_df, main_sheet_name = load_data()
st.session_state.main_sheet_name = main_sheet_name

# --- Column detection helper ---
def detect_column(df_in, options):
    for col in df_in.columns:
        if col.strip().lower() in [opt.lower() for opt in options]:
            return col
    return None

area_col = detect_column(df, ["Area", "Location", "Department"])
category_col = detect_column(df, ["Category", "Type", "Equipment Type"])
tag_col = detect_column(df, ["Valve Tag number", "Tag", "Tag Number"])
function_col = detect_column(df, ["Function", "Function Description"])
serviced_col = detect_column(df, ["Serviced Date", "Last Serviced"])
interval_col = detect_column(df, ["Interval (days)", "Service Interval", "Interval"])
kit_col = detect_column(df, ["Service Kit Part Number", "Kit Number", "Part Number"])
serial_col = detect_column(df, ["Serial Number", "SN"])

required = [area_col, category_col, tag_col, function_col, serviced_col, interval_col]
if any(x is None for x in required):
    show_responsive_logo(main=True)
    st.title("🛠️ Equipment Maintenance Tracker")
    st.error("Missing required columns in the Excel. Check sheet headers and retry.")
    st.stop()

df[serviced_col] = pd.to_datetime(df[serviced_col], errors="coerce")

def get_status(row):
    if pd.isnull(row[serviced_col]) or pd.isnull(row[interval_col]):
        return "⚪ Unknown"
    try:
        next_due = row[serviced_col] + timedelta(days=int(row[interval_col]))
    except Exception:
        return "⚪ Unknown"
    today = datetime.today()
    if today > next_due:
        return "🔴 Overdue"
    elif today > next_due - timedelta(days=7):
        return "🟠 Due Soon"
    else:
        return "🟢 OK"

df["Status"] = df.apply(get_status, axis=1)

total_count = len(df)
overdue_count = int(df["Status"].astype(str).str.contains("Overdue", na=False).sum())
due_soon_count = int(df["Status"].astype(str).str.contains("Due Soon", na=False).sum())
ok_count = int(df["Status"].astype(str).str.contains("OK", na=False).sum())
overdue_plus_due_count = overdue_count + due_soon_count

with st.sidebar:
    show_responsive_logo(main=False)
    st.markdown("---")
    st.header("User")
    if not st.session_state.auth:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pw")
        if st.button("Sign in"):
            user = USERS.get(username.strip())
            if user and hashlib.sha256((SALT + password).encode()).hexdigest() == user["hash"]:
                st.session_state.auth = True
                st.session_state.user = username.strip()
                st.session_state.role = user["role"]
                st.success(f"Signed in as {st.session_state.user} ({st.session_state.role})")
                st.rerun()
            else:
                st.error("Invalid credentials")
    else:
        st.markdown(f"**{st.session_state.user}**")
        st.markdown(f"Role: **{st.session_state.role}**")
        if st.button("Sign out"):
            st.session_state.auth = False
            st.session_state.user = None
            st.session_state.role = None
            st.session_state.view_mode = "home"
            st.session_state.view_tag = None
            st.session_state.editing_tag = None
            st.rerun()

    st.markdown("---")
    smart_options = [
        f"All ({total_count})",
        f"Overdue ({overdue_count})",
        f"Due Soon ({due_soon_count})",
        f"Overdue + Due Soon ({overdue_plus_due_count})",
        f"OK ({ok_count})",
    ]
    default_index = 0
    if "smart_filter_display" in st.session_state and st.session_state.smart_filter_display in smart_options:
        default_index = smart_options.index(st.session_state.smart_filter_display)
    st.selectbox("Show items", smart_options, index=default_index, key="smart_filter_display")

    st.markdown("---")
    if st.session_state.auth and st.session_state.role == "Supervisor":
        st.markdown("### Company Logo")
        uploaded_logo = st.file_uploader("Upload logo PNG or JPEG", type=["png", "jpg", "jpeg"], key="logo_uploader")
        if uploaded_logo is not None:
            st.session_state.logo_bytes = uploaded_logo.read()
            st.success("Logo uploaded")

    st.markdown("---")
    st.markdown("Demo credentials")
    st.write("Supervisor: supervisor / supervisor123")
    st.write("Technician: technician / tech123")

if not st.session_state.auth:
    st.markdown("<br>", unsafe_allow_html=True)
    show_responsive_logo(main=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div style="max-width:780px;">'
        '<h2 style="color:#374151;font-family:Segoe UI, Roboto, Arial;">Equipment Maintenance Tracker</h2>'
        '<p style="color:#6b7280;font-family:Segoe UI, Roboto, Arial;margin-top:-10px;">'
        'Please sign in from the sidebar to continue.</p></div>',
        unsafe_allow_html=True
    )
    st.stop()

def show_header(title="Equipment Maintenance Tracker", subtitle=None):
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        show_responsive_logo(main=True)
    with col_title:
        st.markdown(
            """
            <style>
            .em-title { font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial; font-size:32px; font-weight:700; color:#111827; margin-bottom:4px; }
            .em-sub { font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial; font-size:14px; color:#6b7280; margin-top:0; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="em-title">{title}</div>', unsafe_allow_html=True)
        if subtitle:
            st.markdown(f'<div class="em-sub">{subtitle}</div>', unsafe_allow_html=True)

show_header(
    title="Equipment Maintenance Tracker",
    subtitle="Maintain uptime with clear history and proactive alerts"
)
st.caption(f"Signed in as {st.session_state.user} — {st.session_state.role}")

def display_to_mode(display: str) -> str:
    if "Overdue + Due Soon" in display:
        return "Overdue+DueSoon"
    if display.startswith("Overdue ("):
        return "Overdue"
    if display.startswith("Due Soon ("):
        return "Due Soon"
    if display.startswith("OK ("):
        return "OK"
    return "All"

selected_mode = display_to_mode(st.session_state.smart_filter_display)

def apply_smart_filter(df_in: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == "All":
        return df_in
    if mode == "Overdue":
        return df_in[df_in["Status"].astype(str).str.contains("Overdue", na=False)]
    if mode == "Due Soon":
        return df_in[df_in["Status"].astype(str).str.contains("Due Soon", na=False)]
    if mode == "Overdue+DueSoon":
        mask = df_in["Status"].astype(str).str.contains("Overdue", na=False) | df_in["Status"].astype(str).str.contains("Due Soon", na=False)
        return df_in[mask]
    if mode == "OK":
        return df_in[df_in["Status"].astype(str).str.contains("OK", na=False)]
    return df_in

# =========================
# Home view
# =========================
if st.session_state.view_mode == "home":
    st.subheader("🏠 Home")
    st.markdown("Search equipment by tag number. Use the Smart Filter in the sidebar to limit results.")

    query = st.text_input("🔎 Search by tag number", value="", placeholder="e.g., BD711, V006, PSTM", key="home_search")
    results = pd.DataFrame()
    if query.strip():
        matched = df[df[tag_col].astype(str).str.contains(query.strip(), case=False)].copy()
        results = apply_smart_filter(matched, selected_mode)

    if query.strip():
        st.markdown(f"**Results:** {len(results)} found (filter: {st.session_state.smart_filter_display})")
        if results.empty:
            st.info("No matches. Try a different tag or adjust the Smart Filter.")
        else:
            for _, row in results.iterrows():
                cols = st.columns([3, 2, 2, 1])
                with cols[0]:
                    st.write(f"**{row[tag_col]}** — {row.get(function_col, '')}")
                with cols[1]:
                    st.write(f"**Area:** {row.get(area_col, '')}")
                with cols[2]:
                    st.write(f"**Category:** {row.get(category_col, '')}")
                with cols[3]:
                    if st.button("Open", key=f"open_{row[tag_col]}"):
                        st.session_state.view_tag = row[tag_col]
                        st.session_state.view_mode = "detail"
                        st.rerun()
    else:
        st.info("Type a tag to begin searching or browse all equipment.")

    st.markdown("---")
    if st.button("📂 Browse all by area/category"):
        st.session_state.view_mode = "main"
        st.rerun()

# =========================
# Main view (browse + quick update)
# =========================
elif st.session_state.view_mode == "main":
    st.subheader("Browse and update equipment")
    areas = sorted([x for x in df[area_col].dropna().unique()])
    categories = sorted([x for x in df[category_col].dropna().unique()])
    selected_area = st.selectbox("📍 Select area", areas, key="area_select")
    selected_category = st.selectbox("⚙️ Select category", categories, key="cat_select")

    filtered_df = df[(df[area_col] == selected_area) & (df[category_col] == selected_category)].copy()
    filtered_df = apply_smart_filter(filtered_df, selected_mode)

    search_tag = st.text_input("🔍 Search within selected area/category", key="main_search")
    if search_tag:
        filtered_df = filtered_df[filtered_df[tag_col].astype(str).str.contains(search_tag, case=False)]

    st.subheader(f"📋 {selected_category}s in {selected_area} (showing: {st.session_state.smart_filter_display})")

    for _, row in filtered_df.iterrows():
        label = f"{row[tag_col]} — {row.get(function_col, '')}"
        if st.button(label, key=f"btn_{row[tag_col]}"):
            st.session_state.view_tag = row[tag_col]
            st.session_state.view_mode = "detail"
            st.rerun()

    if not filtered_df.empty and st.session_state.role == "Supervisor":
        st.subheader("✏️ Quick update (Supervisor only)")
        edit_tag = st.selectbox("Select tag to edit", filtered_df[tag_col].unique(), key="edit_tag_select")
        edit_row = filtered_df[filtered_df[tag_col] == edit_tag].iloc[0]
        with st.form("edit_form"):
            default_date = edit_row[serviced_col].date() if pd.notnull(edit_row[serviced_col]) else datetime.today().date()
            new_date = st.date_input("Serviced date", value=default_date)
            default_interval = int(edit_row[interval_col]) if pd.notnull(edit_row[interval_col]) else 30
            new_interval = st.number_input("Interval (days)", min_value=1, value=default_interval)
            service_type = st.selectbox("Service type", ["Planned", "Breakdown"])
            new_kit = None
            new_serial = None
            if edit_row[category_col] in ["Valve", "Pump"] and kit_col:
                new_kit = st.text_input("Service kit part number", value=str(edit_row[kit_col]) if pd.notnull(edit_row[kit_col]) else "")
            if edit_row[category_col] == "Instrument" and serial_col:
                new_serial = st.text_input("Serial number", value=str(edit_row[serial_col]) if pd.notnull(edit_row[serial_col]) else "")
            submitted = st.form_submit_button("Update")
            if submitted:
                df.loc[df[tag_col] == edit_tag, serviced_col] = pd.to_datetime(new_date)
                df.loc[df[tag_col] == edit_tag, interval_col] = int(new_interval)
                if new_kit is not None and kit_col:
                    df.loc[df[tag_col] == edit_tag, kit_col] = new_kit
                if new_serial is not None and serial_col:
                    df.loc[df[tag_col] == edit_tag, serial_col] = new_serial
                new_log = pd.DataFrame([{
                    "Tag": edit_tag,
                    "Serviced Date": pd.to_datetime(new_date),
                    "Interval (days)": int(new_interval),
                    "Service Type": service_type,
                    "Logged At": datetime.now()
                }])
                history_df = pd.concat([history_df, new_log], ignore_index=True)
                save_data(df, history_df, st.session_state.main_sheet_name)
                st.cache_data.clear()
                st.success("✅ Equipment updated and history logged!")
                st.rerun()

    if not filtered_df.empty and st.session_state.role != "Supervisor":
        st.info("You are signed in as a Technician and can only view records. Editing is restricted to Supervisors.")

    st.markdown("---")
    if st.button("🏠 Go to Home"):
        st.session_state.view_mode = "home"
        st.rerun()

# =========================
# Detail view
# =========================
elif st.session_state.view_mode == "detail":
    st.subheader("🔍 Equipment detail view")
    if not st.session_state.view_tag or df[df[tag_col] == st.session_state.view_tag].empty:
        st.info("No equipment selected. Returning to Home.")
        st.session_state.view_mode = "home"
        st.session_state.view_tag = None
        st.rerun()

    selected_tag = st.session_state.view_tag
    item = df[df[tag_col] == selected_tag].iloc[0]
    serviced_date = item[serviced_col].date() if pd.notnull(item[serviced_col]) else "Not recorded"
    next_due = ((item[serviced_col] + timedelta(days=int(item[interval_col]))).date()
                if pd.notnull(item[serviced_col]) and pd.notnull(item[interval_col]) else "Unknown")

    status_icon = "⚪"
    if isinstance(item["Status"], str):
        if "OK" in item["Status"]:
            status_icon = "🟢"
        elif "Due Soon" in item["Status"]:
            status_icon = "🟠"
        elif "Overdue" in item["Status"]:
            status_icon = "🔴"

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🧾 Equipment info")
        st.write(f"**Tag:** {item[tag_col]}")
        st.write(f"**Function:** {item.get(function_col, '')}")
        st.write(f"**Area:** {item[area_col]}")
        st.write(f"**Category:** {item[category_col]}")
        if item[category_col] in ["Valve", "Pump"] and kit_col:
            st.write(f"**Service kit part number:** {item.get(kit_col, '')}")
        elif item[category_col] == "Instrument" and serial_col:
            st.write(f"**Serial number:** {item.get(serial_col, '')}")

    with col2:
        st.markdown("### 🛠️ Maintenance info")
        st.write(f"**Serviced date:** {serviced_date}")
        st.write(f"**Interval (days):** {item.get(interval_col, '')}")
        st.write(f"**Next due:** {next_due}")
        st.write(f"**Status:** {status_icon} {item['Status']}")

    st.markdown("### 📜 Service history")
    if "Tag" in history_df.columns:
        item_history = history_df[history_df["Tag"] == selected_tag].copy()
    else:
        if tag_col in history_df.columns:
            item_history = history_df[history_df[tag_col] == selected_tag].copy()
        else:
            item_history = pd.DataFrame()

    for colname in ["Serviced Date", "Interval (days)", "Service Type", "Logged At"]:
        if colname not in item_history.columns:
            item_history[colname] = pd.NA

    if item_history.empty:
        st.info("No service history found.")
    else:
        item_history["Serviced Date"] = pd.to_datetime(item_history["Serviced Date"], errors="coerce")
        item_history = item_history.sort_values("Serviced Date", ascending=False)
        st.dataframe(item_history[["Serviced Date", "Interval (days)", "Service Type", "Logged At"]], use_container_width=True)

    st.markdown("---")
    cols_nav = st.columns([1, 1, 6])
    with cols_nav[0]:
        if st.button("🔙 Back to List"):
            st.session_state.view_mode = "main"
            st.session_state.view_tag = None
            st.rerun()
    with cols_nav[1]:
        if st.button("🏠 Home"):
            st.session_state.view_mode = "home"
            st.session_state.view_tag = None
            st.rerun()

    if st.session_state.role == "Supervisor":
        st.markdown("### Supervisor edit")
        if st.button("Edit this item"):
            st.session_state.editing_tag = selected_tag
            st.rerun()

        if st.session_state.editing_tag == selected_tag:
            edit_row = df[df[tag_col] == selected_tag].iloc[0]
            with st.form("detail_edit_form"):
                new_date = st.date_input(
                    "Serviced date",
                    value=edit_row[serviced_col].date() if pd.notnull(edit_row[serviced_col]) else datetime.today().date()
                )
                new_interval = st.number_input(
                    "Interval (days)",
                    min_value=1,
                    value=int(edit_row[interval_col]) if pd.notnull(edit_row[interval_col]) else 30
                )
                service_type = st.selectbox("Service type", ["Planned", "Breakdown"])
                new_kit = None
                new_serial = None
                if edit_row[category_col] in ["Valve", "Pump"] and kit_col:
                    new_kit = st.text_input(
                        "Service kit part number",
                        value=str(edit_row[kit_col]) if pd.notnull(edit_row[kit_col]) else ""
                    )
                if edit_row[category_col] == "Instrument" and serial_col:
                    new_serial = st.text_input(
                        "Serial number",
                        value=str(edit_row[serial_col]) if pd.notnull(edit_row[serial_col]) else ""
                    )
                submitted = st.form_submit_button("Save changes")
                if submitted:
                    df.loc[df[tag_col] == selected_tag, serviced_col] = pd.to_datetime(new_date)
                    df.loc[df[tag_col] == selected_tag, interval_col] = int(new_interval)
                    if new_kit is not None and kit_col:
                        df.loc[df[tag_col] == selected_tag, kit_col] = new_kit
                    if new_serial is not None and serial_col:
                        df.loc[df[tag_col] == selected_tag, serial_col] = new_serial
                    new_log = pd.DataFrame([{
                        "Tag": selected_tag,
                        "Serviced Date": pd.to_datetime(new_date),
                        "Interval (days)": int(new_interval),
                        "Service Type": service_type,
                        "Logged At": datetime.now()
                    }])
                    history_df = pd.concat([history_df, new_log], ignore_index=True)
                    save_data(df, history_df, st.session_state.main_sheet_name)
                    st.cache_data.clear()
                    st.success("✅ Changes saved")
                    st.session_state.editing_tag = None
                    st.rerun()
    else:
        st.info("Editing is restricted to Supervisors.")
