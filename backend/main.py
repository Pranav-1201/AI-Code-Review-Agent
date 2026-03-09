from fastapi import FastAPI
from backend.database.connection import init_db

app = FastAPI()

# Initialize database when app starts
init_db()


@app.get("/")
def root():
    return {"message": "AI Code Review Agent running"}