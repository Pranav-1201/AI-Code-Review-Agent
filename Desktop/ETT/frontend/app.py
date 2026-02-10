import streamlit as st
import requests

st.set_page_config(page_title="Explainable AI Code Review Agent", layout="wide")

st.title("🧠 Explainable AI Code Review Agent")
st.write("Submit your code and get explainable feedback powered by LLMs + RAG.")

# Backend URL (do NOT hardcode localhost later — Docker will override)
BACKEND_URL = "http://backend:8000"


st.subheader("📝 Code Input")

language = st.selectbox(
    "Select Programming Language",
    ["Python", "C++", "C", "Java"]
)

code = st.text_area(
    "Paste your code here",
    height=300,
    placeholder="Enter your source code..."
)

if st.button("Analyze Code"):
    if not code.strip():
        st.warning("Please enter some code before analyzing.")
    else:
        with st.spinner("Checking backend status..."):
            try:
                response = requests.get(f"{BACKEND_URL}/health")

                if response.status_code == 200:
                    st.success("Backend is healthy and reachable ✅")
                    st.info("🚧 Code analysis API is not exposed yet.")
                    st.json(response.json())
                else:
                    st.error("Backend responded, but health check failed.")
                    st.text(response.text)

            except Exception as e:
                st.error("Failed to connect to backend.")
                st.text(str(e))

