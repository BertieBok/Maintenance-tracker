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

# --- Sidebar with login + filters ---
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
    smart_options = [
        f"All ({total_count})",
        f"Overdue ({overdue_count})",
        f"Due Soon ({due_soon_count})",
        f"Overdue + Due Soon ({overdue_plus_due_count})",
        f"OK ({ok_count})",
    ]
    # Determine default index based on prior selection if present
    prior = st.session_state.get("smart_filter_display")
    default_index = smart_options.index(prior) if prior in smart_options else 0

    # Use a widget key and DO NOT reassign to session_state manually
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

# --- Main content rendering (simple, non-blank) ---
show_responsive_logo(main=True)
st.title("Equipment overview")

# Stats row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total", total_count)
c2.metric("Overdue", overdue_count)
c3.metric("Due soon", due_soon_count)
c4.metric("OK", ok_count)

# Apply smart filter selection
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
# else: "All" keeps full df

# Search and view mode controls
st.markdown("---")
search = st.text_input("Search by tag, area, or function", "")
if search.strip():
    q = search.strip().lower()
    filtered_df = filtered_df[
        filtered_df.apply(
            lambda r: any(
                str(r.get(col, "")).lower().find(q) >= 0
                for col in [tag_col, area_col, function_col, category_col]
                if col is not None
            ),
            axis=1,
        )
    ]

# Role-based note
if st.session_state.role == "Technician":
    st.info("You are in view-only mode.")
else:
    st.success("Supervisor mode: you can update records below.")

# Show table (basic)
st.dataframe(
    filtered_df[
        [col for col in [tag_col, area_col, category_col, function_col, serviced_col, interval_col, "Status"] if col is not None]
    ],
    use_container_width=True,
)

# Optional: simple update form for supervisors (update serviced date)
if st.session_state.role == "Supervisor":
    st.markdown("---")
    st.subheader("Quick update: serviced date")
    tags = filtered_df[tag_col].dropna().astype(str).unique().tolist() if tag_col else []
    if tags:
        upd_tag = st.selectbox("Select tag", tags)
        upd_date = st.date_input("Serviced date", datetime.today().date())
        upd_interval = st.number_input("Interval (days)", min_value=1, value=30, step=1)
        if st.button("Save update"):
            # Update main df
            idx = df[df[tag_col].astype(str) == str(upd_tag)].index
            if len(idx) > 0:
                df.loc[idx, serviced_col] = pd.to_datetime(upd_date)
                df.loc[idx, interval_col] = int(upd_interval)
                # Append to history
                new_row = {
                    "Tag": upd_tag,
                    "Serviced Date": pd.to_datetime(upd_date),
                    "Interval (days)": int(upd_interval),
                    "Service Type": "Routine",
                    "Logged At": pd.Timestamp.utcnow(),
                }
                history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
                # Persist
                save_data(df, history_df, st.session_state.main_sheet_name)
                st.success(f"Updated {upd_tag}")
                st.rerun()
            else:
                st.error("Tag not found in main sheet.")
    else:
        st.info("No tags available to update.")
