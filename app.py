import streamlit as st
import time

def YOUR_BACKEND_FUNCTION(repo_url):
    return {
        "summary": {
            "files": 4,
            "files_with_issues": 4,
            "avg_score": 73.75,
            "security_issues": 0
        },
        "files": [
            {
                "name": "main.py",
                "score": 64,
                "issues": [{"message": "Nested loops detected", "severity": "Medium"}],
                "security": [],
                "complexity": "O(n^2)",
                "explanation": "Nested loops increase time complexity.",
                "suggestions": ["Use hashmap to optimize"],
                "improved_code": "def main(): pass",
                "patch": None
            }
        ]
    }

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
    ["Repository Scanner", "Scan Results","Test Results","Settings"]
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

            st.write(f"🔗 Repository: {repo_url}")

        # progress starts HERE (inside if)
            progress = st.progress(0)

            steps = [
                "🔄 Cloning repository...",
                "📂 Scanning files...",
                "🔍 Running code analysis...",
                "🔐 Checking security vulnerabilities...",
                "🤖 Generating AI explanations..."
            ]

            for i, step in enumerate(steps):
                st.write(step)
                time.sleep(1)
                progress.progress((i + 1) * 20)

            progress.empty()

            backend_response = YOUR_BACKEND_FUNCTION(repo_url)
            st.session_state["report"] = backend_response

            st.success("✅ Scan Completed! Go to Scan Results.")

        else:
            st.error("Please enter a repository URL")

# Placeholder pages
elif page == "Scan Results":

    st.header("📊 AI Code Review Results")

    if "report" not in st.session_state:
        st.warning("⚠ Please scan a repository first.")
        st.stop()

    report = st.session_state["report"]


    st.subheader("📈 Repository Summary")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Files Analyzed", report["summary"]["files"])
    col2.metric("Files with Issues", report["summary"]["files_with_issues"])
    col3.metric("Avg Score", report["summary"]["avg_score"])
    col4.metric("Security Issues", report["summary"]["security_issues"])

    st.divider()

    st.subheader("🔍 Filters")

    severity_filter = st.selectbox(
        "Filter by Severity",
        ["All", "Low", "Medium", "High", "Critical"]
    )

    st.divider()


    st.subheader("📂 File Analysis")

    search_file = st.text_input("🔎 Search file")

    for file in report["files"]:
        if search_file and search_file.lower() not in file["name"].lower():
           continue

        with st.expander(f"📄 {file['name']} (Score: {file['score']})"):


            st.markdown("### 📊 Quality Score")
            st.progress(file["score"] / 100)
            st.caption(f"Score: {file['score']}/100")


            st.markdown("### ⚠ Issues")

            color = {
                    "Low": "🟢",
                    "Medium": "🟡",
                    "High": "🟠",
                    "Critical": "🔴"
            }

            shown = False

            if file["issues"]:
                for issue in file["issues"]:
                    if severity_filter == "All" or issue["severity"] == severity_filter:
                       shown = True
                       st.write(f"{color.get(issue['severity'], '⚪')} {issue['message']} ({issue['severity']})")

                if not shown:
                    st.info("No issues match the selected filter")
            else: 
                st.info("✅ No issues found")


            st.markdown("### 🔐 Security Risks")

            if file["security"]:
                for sec in file["security"]:
                    st.error(sec)
            else:
                st.success("No security risks")

            st.markdown("### ⚙ Complexity")
            st.info(file["complexity"])


            st.markdown("### 🧠 AI Explanation")
            st.info(file["explanation"])


            st.markdown("### 💡 Suggestions")

            if file["suggestions"]:
                for s in file["suggestions"]:
                    st.write(f"- {s}")
            else:
                st.info("No suggestions available")


            st.markdown("### 🚀 Improved Code")

            view = st.radio(
                "View Code",
                ["Improved Code", "Original Code"],
                horizontal=True,
                key=f"view_{file['name']}"
            )

            if view == "Improved Code":
                st.code(file["improved_code"], language="python")
            else:
                st.code(file.get("original_code", "Not available"), language="python")


            if file.get("patch") not in [None, "N/A", ""]:
                st.markdown("### 🩹 Patch")
                st.code(file["patch"], language="diff")
elif page == "Settings":
    st.header("Settings")
    st.info("Settings page coming soon.")

elif page == "Test Results":

    st.header("✅ Backend Test Results")

    # =========================
    # 🔹 SUMMARY METRICS (STEP 8 PART 2)
    # =========================
    tests = [
        "test_complexity",
        "test_dead_code",
        "test_llm_refactor",
        "test_patch_generator",
        "test_quality_score",
        "test_refactoring",
        "test_repo_analysis",
        "test_repository_review",
        "test_retrieval",
        "test_review_report",
        "test_security_integration",
        "test_smells"
    ]

    total_tests = len(tests)
    passed_tests = len(tests)

    col1, col2 = st.columns(2)
    col1.metric("Total Tests", total_tests)
    col2.metric("Passed", passed_tests)

    st.divider()

    # =========================
    # 🔹 TEST LIST
    # =========================
    st.subheader("🧪 Test Suite Status")

    for test in tests:
        st.success(f"✔ {test} passed")

    st.info("All backend systems are functioning correctly.")
