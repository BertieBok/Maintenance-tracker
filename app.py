import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import base64
import sys
import os

# -------------------------------------------------------------------
# Helper to locate data files when running as a PyInstaller one-file bundle
def resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)
# -------------------------------------------------------------------

st.set_page_config(page_title="Equipment Maintenance Tracker", layout="wide")

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
if "smart_filter_display" not in st.session_state:
    st.session_state.smart_filter_display = None
if "page_number" not in st.session_state:
    st.session_state.page_number = 0
if "page_size" not in st.session_state:
    st.session_state.page_size = 25

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

# --- Compute status ---
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

# --- Sidebar with login + single smart-filter widget ---
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
                # Force a default view after login
                if st.session_state.role == "Supervisor":
                    st.session_state.view_mode = "main"
                else:
                    st.session_state.view_mode = "home"
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
    # Single smart filter defined here (unique creation)
    smart_options = [
        f"All ({total_count})",
        f"Overdue ({overdue_count})",
        f"Due Soon ({due_soon_count})",
        f"Overdue + Due Soon ({overdue_plus_due_count})",
        f"OK ({ok_count})",
    ]
    prior = st.session_state.get("smart_filter_display")
    default_index = smart_options.index(prior) if prior in smart_options else 0
    st.selectbox("Show items", smart_options, index=default_index, key="smart_filter_display")

    st.markdown("---")
    if st.session_state.auth and st.session_state.role == "Supervisor":
        st.markdown("### Company logo")
        uploaded_logo = st.file_uploader("Upload logo PNG or JPEG", type=["png", "jpg", "jpeg"], key="logo_uploader")
        if uploaded_logo is not None:
            st.session_state.logo_bytes = uploaded_logo.read()
            st.success("Logo uploaded")

    st.markdown("---")
    st.markdown("Demo credentials")
    st.write("Supervisor: supervisor / supervisor123")
    st.write("Technician: technician / tech123")

# --- Gatekeeper: show sign-in prompt if not authenticated ---
if not st.session_state.auth:
    st.markdown("<br>", unsafe_allow_html=True)
    show_responsive_logo(main=True)
    st.title("🛠️ Equipment Maintenance Tracker")
    st.write("Please sign in from the sidebar to continue.")
    st.stop()

# --- Professional Home page (uses the single smart filter defined in sidebar) ---
show_responsive_logo(main=True)
st.markdown("<br>", unsafe_allow_html=True)
st.header("Equipment Maintenance Dashboard")

# Top KPI cards
k1, k2, k3, k4 = st.columns([1.4, 1, 1, 1])
k1.metric("Total Assets", total_count)
k2.metric("Overdue", overdue_count)
k3.metric("Due Soon", due_soon_count)
k4.metric("OK", ok_count)

st.markdown("---")

# Search and quick filters row
scol1, scol2, scol3 = st.columns([3, 1.6, 1.2])

with scol1:
    search_term = st.text_input(
        "Search by Tag, Area, Category or Function",
        value="",
        placeholder="Type tag number, area, category, or function and press Enter"
    )

with scol2:
    # Read single smart filter value created in sidebar
    home_smart_options = smart_options  # reuse same list
    prior_home = st.session_state.get("smart_filter_display")
    default_index_home = home_smart_options.index(prior_home) if prior_home in home_smart_options else 0
    # Display the current selection as a non-editable element to avoid duplicate widget keys
    st.write(f"Filter: **{home_smart_options[default_index_home]}**")

with scol3:
    today = datetime.today().date()
    dr_start = st.date_input("Serviced since", value=today - timedelta(days=30), key="dr_start")
    dr_end = st.date_input("Serviced until", value=today, key="dr_end")

st.markdown("---")

# Build filtered_df from smart filter (sidebar), then search, then date-range
selection = st.session_state.get("smart_filter_display") or smart_options[0]
filtered_df = df.copy()

if "Overdue + Due Soon" in selection:
    filtered_df = df[df["Status"].isin(["🔴 Overdue", "🟠 Due Soon"])]
elif "Overdue" in selection and "Overdue + Due Soon" not in selection:
    filtered_df = df[df["Status"] == "🔴 Overdue"]
elif "Due Soon" in selection:
    filtered_df = df[df["Status"] == "🟠 Due Soon"]
elif "OK" in selection:
    filtered_df = df[df["Status"] == "🟢 OK"]
# else All -> keep all

# Apply global search if provided
if search_term and search_term.strip():
    q = search_term.strip().lower()
    cols_to_search = [tag_col, area_col, category_col, function_col]
    cols_to_search = [c for c in cols_to_search if c is not None]
    if cols_to_search:
        mask = pd.Series(False, index=filtered_df.index)
        for c in cols_to_search:
            mask = mask | filtered_df[c].astype(str).str.lower().str.contains(q, na=False)
        filtered_df = filtered_df[mask]

# Apply serviced date range filter on serviced_col
try:
    sens = pd.to_datetime(filtered_df[serviced_col], errors="coerce").dt.date
    filtered_df = filtered_df[(sens >= dr_start) & (sens <= dr_end)]
except Exception:
    pass

# Two-column layout: left -> results table; right -> summary / recent activity
left, right = st.columns([3, 1.2])

with right:
    st.subheader("Summary")
    st.write(f"Showing: **{len(filtered_df)}** items")
    st.markdown("")
    st.subheader("Recent services")
    recent = df.dropna(subset=[serviced_col]).sort_values(by=serviced_col, ascending=False).head(6)
    if not recent.empty:
        st.table(
            recent[[tag_col, area_col, serviced_col]].rename(
                columns={tag_col: "Tag", area_col: "Area", serviced_col: "Serviced"}
            )
        )
    else:
        st.write("No recent services found")

with left:
    st.subheader("Search results")
    display_cols = [tag_col, area_col, category_col, function_col, serviced_col, interval_col, "Status"]
    display_cols = [c for c in display_cols if c is not None]
    page_size = st.selectbox("Rows per page", [10, 25, 50, 100], index=[10,25,50,100].index(st.session_state.get("page_size",25)), key="page_size_select")
    st.session_state.page_size = page_size
    start = st.session_state.page_number * page_size
    end = start + page_size
    page_df = filtered_df.iloc[start:end]

    if page_df.empty:
        st.info("No results. Try clearing search or adjusting filters.")
    else:
        st.dataframe(page_df[display_cols].reset_index(drop=True), use_container_width=True)

        sel_options = page_df[tag_col].dropna().astype(str).unique().tolist() if tag_col in page_df.columns else []
        if sel_options:
            sel_tag = st.selectbox("Select a tag to view details", options=sel_options, index=0, key="sel_tag_box")
            detail_row = df[df[tag_col].astype(str) == str(sel_tag)]
            if not detail_row.empty:
                r = detail_row.iloc[0]
                st.markdown("### Details")
                st.write(f"**Tag:** {r.get(tag_col,'')}")
                st.write(f"**Area:** {r.get(area_col,'')}")
                st.write(f"**Category:** {r.get(category_col,'')}")
                st.write(f"**Function:** {r.get(function_col,'')}")
                st.write(f"**Last Serviced:** {r.get(serviced_col,'')}")
                st.write(f"**Interval (days):** {r.get(interval_col,'')}")
                st.write(f"**Status:** {r.get('Status','')}")
                if st.session_state.role == "Supervisor":
                    st.markdown("---")
                    if st.button("Mark serviced today", key=f"mark_serviced_{sel_tag}"):
                        idx = df[df[tag_col].astype(str) == str(sel_tag)].index
                        if len(idx) > 0:
                            df.loc[idx, serviced_col] = pd.to_datetime(datetime.today().date())
                            new_row = {
                                "Tag": sel_tag,
                                "Serviced Date": pd.to_datetime(datetime.today().date()),
                                "Interval (days)": int(df.loc[idx, interval_col].iloc[0]) if interval_col in df.columns else 30,
                                "Service Type": "Routine",
                                "Logged At": pd.Timestamp.utcnow(),
                            }
                            history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
                            save_data(df, history_df, st.session_state.main_sheet_name)
                            st.success(f"Marked {sel_tag} serviced today")
                            st.experimental_rerun()

# Pagination controls
st.markdown("---")
colp1, colp2, colp3 = st.columns([1, 1, 6])
with colp1:
    if st.button("Previous", key="page_prev") and st.session_state.page_number > 0:
        st.session_state.page_number -= 1
with colp2:
    if st.button("Next", key="page_next"):
        max_page = max(0, (len(filtered_df) - 1) // page_size)
        if st.session_state.page_number < max_page:
            st.session_state.page_number += 1

st.markdown("<br>", unsafe_allow_html=True)

# --- Optional Supervisor quick update form (kept at bottom for convenience) ---
if st.session_state.role == "Supervisor":
    st.markdown("---")
    st.subheader("Quick update: serviced date")
    tags = df[tag_col].dropna().astype(str).unique().tolist() if tag_col else []
    if tags:
        upd_tag = st.selectbox("Select tag", tags, key="upd_tag_box")
        upd_date = st.date_input("Serviced date", datetime.today().date(), key="upd_date")
        upd_interval = st.number_input("Interval (days)", min_value=1, value=30, step=1, key="upd_interval")
        if st.button("Save update", key="save_update"):
            idx = df[df[tag_col].astype(str) == str(upd_tag)].index
            if len(idx) > 0:
                df.loc[idx, serviced_col] = pd.to_datetime(upd_date)
                df.loc[idx, interval_col] = int(upd_interval)
                new_row = {
                    "Tag": upd_tag,
                    "Serviced Date": pd.to_datetime(upd_date),
                    "Interval (days)": int(upd_interval),
                    "Service Type": "Routine",
                    "Logged At": pd.Timestamp.utcnow(),
                }
                history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df, history_df, st.session_state.main_sheet_name)
                st.success(f"Updated {upd_tag}")
                st.experimental_rerun()
            else:
                st.error("Tag not found in main sheet.")
    else:
        st.info("No tags available to update.")
