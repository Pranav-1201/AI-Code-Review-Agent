import streamlit as st

# Page configuration
st.set_page_config(
    page_title="AI Code Review Agent",
    layout="wide"
)

# Sidebar navigation
st.sidebar.title("Navigation")
option = st.sidebar.selectbox(
    "Select Option",
    ["Home", "Analyze Repository", "Security Dashboard"]
)

# Main dashboard
st.title("AI Code Review Agent")
st.write("An AI-powered system to analyze repositories and generate code reviews.")

# Different sections
if option == "Home":
    st.header("Welcome")
    st.write("Use this tool to analyze GitHub repositories and receive automated code review feedback.")

elif option == "Analyze Repository":
    st.header("Repository Analysis")
    repo_url = st.text_input("Enter GitHub Repository URL")

    if st.button("Analyze"):
        st.success("Repository submitted for analysis.")

elif option == "Security Dashboard":
    st.header("Security Issues")
    st.write("Detected vulnerabilities will appear here.")
