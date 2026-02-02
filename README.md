# Explainable AI Code Review Agent 🚀

An **Explainable AI Code Review Agent** powered by **Large Language Models (LLMs)** that analyzes source code, detects bugs, evaluates complexity, and provides **clear, human-readable explanations** for every suggestion. The system uses **Retrieval-Augmented Generation (RAG)** for grounded reasoning and is fully **Dockerized** for portability and scalability.

---

## ✨ Key Features

* 🧠 **LLM-powered code analysis** (logic errors, code smells, inefficiencies)
* 📘 **Explainable AI outputs** – not just what is wrong, but *why*
* 📊 **Time & space complexity estimation**
* 🔐 **Basic security and unsafe pattern detection**
* 🔎 **RAG with FAISS** for grounded explanations using best practices
* 🤖 **AI Agent architecture** using LangChain tools
* 🐳 **Dockerized microservices** for reproducible deployment
* ☸️ **Kubernetes-ready** architecture (optional scaling)

---

## 🏗️ System Architecture

```
User
 ↓
Web UI (Streamlit)
 ↓
FastAPI Backend
 ↓
LangChain Agent
 ├── Bug Detection Tool
 ├── Complexity Analyzer
 ├── Static Rule Engine
 ├── RAG Retriever (FAISS)
 ↓
LLM (Hugging Face Models)
 ↓
Explainable Review Report
```

Each major component runs as an independent service and can be containerized and scaled.

---

## 🧰 Tech Stack

**AI / NLP**

* Hugging Face Transformers
* Open-source code LLMs (CodeBERT, CodeLLaMA, Mistral)
* LangChain (Agents, Tools, Memory)
* FAISS (Vector Database)

**Backend**

* Python
* FastAPI
* Pydantic

**Frontend**

* Streamlit (lightweight demo UI)

**DevOps**

* Docker & Docker Compose
* Kubernetes (ReplicaSets, Autoscaling, Rolling Updates)

---

## 📁 Project Structure

```
explainable-ai-code-reviewer/
│
├── backend/              # FastAPI backend & core logic
│   ├── app/
│   │   ├── services/     # LLM, RAG, explainability modules
│   │   ├── routes/       # API routes
│   │   └── main.py       # API entry point
│   └── Dockerfile
│
├── rag/                  # RAG ingestion & FAISS index
│   ├── data/
│   ├── ingest.py
│   └── Dockerfile
│
├── frontend/             # Streamlit UI
│   ├── app.py
│   └── Dockerfile
│
├── docker-compose.yml
├── .env
└── README.md
```

---

## 🚀 Getting Started

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-username/explainable-ai-code-reviewer.git
cd explainable-ai-code-reviewer
```

### 2️⃣ Create & Activate Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS/Linux
```

### 3️⃣ Install Dependencies

```bash
pip install -r backend/requirements.txt
```

### 4️⃣ Set Environment Variables

Create a `.env` file:

```env
HUGGINGFACE_TOKEN=your_huggingface_token
```

### 5️⃣ Run Backend Locally

```bash
uvicorn backend.app.main:app --reload
```

---

## 🐳 Running with Docker (Recommended)

```bash
docker compose up --build
```

This starts:

* Backend API
* RAG service
* Frontend UI

---

## 🎯 Use Cases

* Students learning data structures & algorithms
* Beginners understanding coding mistakes
* Interview preparation & practice
* Educational institutions & labs
* Explainable AI demonstrations

---

## ⚠️ Limitations

* LLM outputs may vary depending on prompt formulation
* Very complex bugs may require deeper fine-tuning
* Code execution is not performed (analysis-only)

---

## 🔮 Future Enhancements

* VS Code / IDE plugin
* Reinforcement learning from user feedback
* Multi-language execution sandbox
* GitHub Pull Request integration
* Advanced hallucination detection

---

## 📚 Learning Outcomes

This project demonstrates:

* Practical use of LLMs for real-world problems
* Explainable AI system design
* RAG pipelines using FAISS
* Agent-based AI architectures
* Docker & Kubernetes-based deployment

---

## 📄 License

This project is for academic and educational purposes.

---

**⭐ If you find this project useful, consider starring the repository!**
