FROM python:3.12-slim

# Spriječi generiranje .pyc datoteka i osiguraj čist stdout ispis
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instaliraj potrebne biblioteke
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Kopiraj izvorni kod
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY run.py /app/run.py

# Otvori portove za Web i DNS
EXPOSE 8000/tcp
EXPOSE 5053/udp
EXPOSE 53/udp

# Zadani start
CMD ["python", "run.py", "--dns-port", "5053", "--web-port", "8000"]
