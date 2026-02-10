# Python 3.10 for consistency
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy frontend requirements (if present)
COPY requirements.txt .

# Install frontend dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy Streamlit app
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
