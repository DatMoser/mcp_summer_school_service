FROM python:3.11-slim
WORKDIR /app

# Install Google Cloud SDK
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - \
    && apt-get update && apt-get install -y google-cloud-sdk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV PORT 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]