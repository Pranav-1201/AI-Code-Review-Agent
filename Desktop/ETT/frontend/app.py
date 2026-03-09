import streamlit as st

# Page config
st.set_page_config(
    page_title="AI Code Review Dashboard",
    layout="wide"
)

# Sidebar
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Repository Scanner", "Scan Results", "Settings"]
)

# Main page
st.title("AI Code Review Assistant")

# Repository Scanner Page
if page == "Repository Scanner":

    st.header("Scan GitHub Repository")

    repo_url = st.text_input(
        "Enter GitHub Repository URL",
        placeholder="https://github.com/username/repository"
    )

    scan_button = st.button("Scan Repository")

    if scan_button:
        if repo_url:
            st.success(f"Scanning repository: {repo_url}")
        else:
            st.error("Please enter a repository URL")

# Placeholder pages
elif page == "Scan Results":
    st.header("Scan Results")
    st.info("Results will appear here after scanning.")

elif page == "Settings":
    st.header("Settings")
    st.info("Settings page coming soon.")
