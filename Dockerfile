FROM python:3.11-slim

# Install system dependencies (ffmpeg untuk pemrosesan video dan curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Buat non-root user UID 1000 sesuai standar keamanan Hugging Face Spaces
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860 \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# Salin requirements dan install library Python
COPY --chown=user requirements.txt $HOME/app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Salin seluruh kode aplikasi ke dalam container
COPY --chown=user . $HOME/app

# Pastikan folder data dan recordings memiliki izin tulis
RUN mkdir -p $HOME/app/data $HOME/app/recordings

EXPOSE 7860

CMD ["python", "app.py"]
