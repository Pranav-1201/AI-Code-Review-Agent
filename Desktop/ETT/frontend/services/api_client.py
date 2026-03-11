import requests

API_URL = "http://localhost:8000/analyze"

def analyze_repository(repo_url):
    try:
        response = requests.post(
            API_URL,
            json={"repo_url": repo_url}
        )

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": "Backend returned an error"}

    except Exception as e:
        return {"error": str(e)}