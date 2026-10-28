# CENLAC en un contenedor, para publicarlo en internet (Render, Railway, Fly.io, etc.) con la base en Supabase.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=America/Argentina/Buenos_Aires EN_INTERNET=1 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]
