FROM python:3.12

# Install Chrome for Nova Act
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg2 \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY upload.py .
COPY scrape.py .

ENV NOVA_ACT_API_KEY=""
ENV TASK_MODE="upload"

CMD ["sh", "-c", "python ${TASK_MODE}.py"]
