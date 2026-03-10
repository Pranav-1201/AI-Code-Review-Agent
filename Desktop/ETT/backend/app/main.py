from fastapi import FastAPI

app = FastAPI(title="Explainable AI Code Review Agent")

@app.get("/")
def root():
    return {"status": "Backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}
