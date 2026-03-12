import streamlit as st
from services.api_client import analyze_repository

st.markdown("""
<style>

.main {
    background-color: #0E1117;
}

h1, h2, h3 {
    color: #FAFAFA;
}

.stMetric {
    background-color: #1c1f26;
    padding: 15px;
    border-radius: 10px;
}

.stButton>button {
    background-color: #4CAF50;
    color: white;
    border-radius: 8px;
    height: 3em;
    width: 200px;
}

.stTextInput>div>div>input {
    background-color: #1c1f26;
    color: white;
}

</style>
""", unsafe_allow_html=True)

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
st.title("🤖 AI Code Review Dashboard")
st.caption("Automated repository analysis powered by AI")

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
            result = analyze_repository(repo_url)

            st.write("Analysis Result:")
            st.write(result)
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

col1, col2, col3, col4 = st.columns(4)

col1.metric("Files Analyzed", 120)
col2.metric("Issues Found", 15)
col3.metric("Security Issues", 3)
col4.metric("Code Quality Score", "82%")
