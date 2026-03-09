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

    st.header("AI Code Review Results")

    # Metrics
    col1, col2, col3 = st.columns(3)

    col1.metric("Files Scanned", "24")
    col2.metric("Issues Found", "7")
    col3.metric("Security Warnings", "2")

    st.divider()

    # Issue Table
    st.subheader("Detected Issues")

    issues = [
        {"File": "auth.py", "Issue": "Hardcoded secret key", "Severity": "High"},
        {"File": "db.py", "Issue": "SQL query not parameterized", "Severity": "High"},
        {"File": "utils.py", "Issue": "Unused variable", "Severity": "Low"},
        {"File": "api.py", "Issue": "Missing input validation", "Severity": "Medium"},
    ]

    st.table(issues)

    st.divider()

    # Simple chart
    st.subheader("Issue Severity Distribution")

    chart_data = {
        "Severity": ["High", "Medium", "Low"],
        "Count": [2, 3, 2]
    }

    st.bar_chart(chart_data, x="Severity", y="Count")

elif page == "Settings":
    st.header("Settings")
    st.info("Settings page coming soon.")
