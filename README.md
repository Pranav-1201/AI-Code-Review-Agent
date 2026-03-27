# AI Code Review Agent

An **AI-powered repository analysis platform** that scans GitHub repositories and provides deep insights into **code quality, security vulnerabilities, maintainability, and architectural complexity**.

The system combines **static code analysis, repository graph analysis, and AI-assisted recommendations** to help developers understand and improve their codebases.

---

# Overview

AI Code Review Agent automatically analyzes a repository and generates a detailed review including:

* security risks
* code complexity
* maintainability score
* dependency structure
* duplicate code detection
* architectural insights
* AI-generated refactoring suggestions

It provides these insights through a **modern interactive dashboard** built with React.

The system is designed to behave like an **automated code reviewer for entire repositories**.

---

# Key Features

## Repository Scanning

Analyze any GitHub repository by providing its URL.

The system automatically:

* clones the repository
* parses the source code
* builds dependency graphs
* performs static analysis
* generates a structured review report

---

## Static Code Analysis

The platform performs multiple static analysis techniques:

* AST-based parsing
* call graph generation
* cyclomatic complexity analysis
* dead code detection
* code smell detection

This allows the system to understand **how the codebase is structured and behaves internally**.

---

## Code Quality Evaluation

Each repository is evaluated using several quality metrics:

* cyclomatic complexity
* maintainability indicators
* code smell detection
* structural issues

The system aggregates these metrics into a **repository health score**.

---

## Security Analysis

The platform scans for unsafe programming patterns such as:

* dangerous function usage
* insecure subprocess calls
* unsafe evaluation patterns
* risky system operations

This helps detect **potential vulnerabilities early in development**.

---

## Dependency Analysis

The system analyzes how files depend on each other.

It builds a **repository dependency graph** that helps identify:

* tightly coupled modules
* architectural bottlenecks
* highly dependent files

---

## Duplicate Code Detection

Detects similar code patterns across files.

Helps identify:

* repeated logic
* refactoring opportunities
* maintainability risks.

---

## AI-Powered Code Insights

The platform integrates **LLM-based reasoning** to generate:

* refactoring suggestions
* improvement recommendations
* explanation of detected issues

These suggestions help developers understand **why a problem exists and how to fix it**.

---

## Pull Request Analysis (Architecture Ready)

The system includes a **PR review engine** which can be extended to analyze pull requests and code changes.

---

## Interactive Dashboard

The frontend provides an interactive dashboard with multiple analysis views.

Available pages include:

* Repository Scanner
* Repository Overview
* Scan Results
* File Analysis
* Security Report
* Code Quality
* Dependency Analysis
* Duplicate Detection
* AI Suggestions
* Health Score
* Issue Explorer
* Visualizations
* Scan History
* Export Report
* Settings

This allows developers to explore their repository from **multiple analytical perspectives**.

---

# System Architecture

```
User
↓
React Dashboard (Frontend)
↓
FastAPI Backend
↓
Repository Scanner
│
├── Static Analysis Engine
│   ├── AST Parser
│   ├── Call Graph Builder
│   ├── Complexity Analyzer
│   ├── Dead Code Detector
│   └── Code Smell Detector
│
├── Repository Intelligence
│   ├── Dependency Analyzer
│   ├── Duplicate Detector
│   └── Security Analyzer
│
├── AI Engine
│   ├── LLM Refactor Engine
│   └── RAG Retrieval
│
↓
Review Report Generator
↓
Frontend Visualization
```

---

# Tech Stack

## Backend

* Python
* FastAPI
* AST-based static analysis
* FAISS / vector retrieval
* SQLite database

## Frontend

* React
* TypeScript
* Vite
* TailwindCSS

## AI & Analysis

* Transformers
* Sentence Transformers
* Retrieval-Augmented Generation
* Static code analysis modules

---

# Project Structure

```
AI-Code-Review-Agent
│
├── backend
│   ├── app
│   │   ├── analysis
│   │   │   ├── complexity_analyzer.py
│   │   │   ├── dependency_analyzer.py
│   │   │   ├── duplicate_detector.py
│   │   │   ├── dead_code_detector.py
│   │   │   └── refactoring_engine.py
│   │   │
│   │   ├── services
│   │   │   ├── repo_analyzer.py
│   │   │   ├── security_analyzer.py
│   │   │   ├── scan_manager.py
│   │   │   ├── report_generator.py
│   │   │   └── repository_review_engine.py
│   │   │
│   │   └── routes
│
├── frontend
│   ├── src
│   │   ├── components
│   │   ├── pages
│   │   └── lib
│
├── rag
│   ├── vector_store.py
│   └── ingest.py
│
├── main.py
├── requirements.txt
└── README.md
```

---

# Running the Project Locally

## 1. Clone the Repository

```
git clone https://github.com/Pranav-1201/AI-Code-Review-Agent.git
cd AI-Code-Review-Agent
```

---

# Backend Setup

## Create Virtual Environment

```
python -m venv venv
```

Activate it:

Windows

```
venv\Scripts\activate
```

Mac/Linux

```
source venv/bin/activate
```

---

## Install Dependencies

```
pip install -r requirements.txt
```

---

## Run Backend Server

```
uvicorn main:app --reload
```

Backend runs on:

```
http://localhost:8000
```

---

# Frontend Setup

Open a new terminal.

```
cd frontend
npm install
```

Start the frontend:

```
npm run dev
```

Frontend runs on:

```
http://localhost:5173
```

---

# Using the System

1. Open the dashboard in your browser
2. Enter a GitHub repository URL
3. Start a scan
4. Explore the generated insights

The system will generate:

* repository metrics
* security reports
* dependency graphs
* duplicate detection
* AI suggestions
* visualizations

---

# Future Improvements

Planned enhancements include:

* GitHub OAuth integration
* pull request analysis
* automated refactoring
* CI/CD integration
* IDE plugins
* advanced vulnerability detection

---

# Educational Value

This project demonstrates:

* static code analysis techniques
* AI-assisted code review
* repository architecture analysis
* full-stack AI tooling
* modern developer dashboards

---

# License

This project is intended for **educational and research purposes**.
