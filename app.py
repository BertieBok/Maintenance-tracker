import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
import os
from datetime import datetime

# -----------------------------
# Google Sheets Setup
# -----------------------------
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)
client = gspread.authorize(creds)

SHEET_NAME = "Maintenance Tracker"   # Google Sheet name
MAIN_SHEET = "Equipment"             # tab for main equipment data
HISTORY_SHEET = "Service History"    # tab for service logs

@st.cache_data(show_spinner=False)
def load_data():
    # Load main sheet
    sheet_main = client.open(SHEET_NAME).worksheet(MAIN_SHEET)
    data_main = sheet_main.get_all_records()
    df = pd.DataFrame(data_main)

    # Load history sheet
    try:
        sheet_history = client.open(SHEET_NAME).worksheet(HISTORY_SHEET)
        data_history = sheet_history.get_all_records()
        history = pd.DataFrame(data_history)
    except:
        history = pd.DataFrame(columns=["Tag", "Serviced Date", "Interval (days)", "Service Type", "Logged At"])

    return df, history, MAIN_SHEET

def save_data(df, history, main_sheet_name):
    # Save main sheet
    sheet_main = client.open(SHEET_NAME).worksheet(MAIN_SHEET)
    sheet_main.clear()
    sheet_main.update([df.columns.values.tolist()] + df.values.tolist())

    # Save history sheet
    sheet_history = client.open(SHEET_NAME).worksheet(HISTORY_SHEET)
    sheet_history.clear()
    sheet_history.update([history.columns.values.tolist()] + history.values.tolist())

# -----------------------------
# User Authentication
# -----------------------------
USER_CREDENTIALS = {
    "admin": {"password": "admin123", "role": "Supervisor"},
    "user": {"password": "user123", "role": "Technician"}
}

def login():
    st.sidebar.title("🔐 Login")
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        user = USER_CREDENTIALS.get(username)
        if user and user["password"] == password:
            st.session_state.auth = True
            st.session_state.user = username
            st.session_state.role = user["role"]
        else:
            st.sidebar.error("Invalid credentials")

if "auth" not in st.session_state:
    st.session_state.auth = False
    login()

# -----------------------------
# Main App
# -----------------------------
if st.session_state.auth:
    st.title("🛠️ Equipment Maintenance Tracker (Google Sheets Edition)")
    st.caption(f"Logged in as: {st.session_state.user} ({st.session_state.role})")

    df, history, main_sheet_name = load_data()

    tab_home, tab_browse, tab_detail = st.tabs(["🏠 Home", "📂 Browse", "🔍 Details"])

    # Home Tab
    with tab_home:
        st.subheader("Search by Tag")
        if not df.empty:
            tags = df.iloc[:, 0].dropna().tolist()
            selected_tag = st.selectbox("Select Tag", tags)
            if selected_tag:
                row = df[df.iloc[:, 0] == selected_tag]
                st.write("**Equipment Details:**")
                st.dataframe(row)

    # Browse Tab
    with tab_browse:
        st.subheader("Browse Equipment")
        st.dataframe(df)

    # Detail Tab
    with tab_detail:
        st.subheader("Equipment Details")
        if not df.empty:
            tags = df.iloc[:, 0].dropna().tolist()
            selected_tag = st.selectbox("Select Tag for Details", tags, key="detail_tag")
            if selected_tag:
                row = df[df.iloc[:, 0] == selected_tag]
                st.write("**Details:**")
                st.dataframe(row)

                if st.session_state.role == "Supervisor":
                    st.subheader("✏️ Edit Equipment")
                    edited_values = {}
                    for col in df.columns:
                        edited_values[col] = st.text_input(col, value=row.iloc[0][col])

                    if st.button("Save Changes"):
                        for col in df.columns:
                            df.loc[df.iloc[:, 0] == selected_tag, col] = edited_values[col]
                        save_data(df, history, main_sheet_name)
                        st.success("Changes saved to Google Sheets!")
                else:
                    st.info("You are signed in as a Technician and cannot edit records.")

    # Logout
    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.experimental_rerun()

else:
    st.warning("Please log in to access the app.")
