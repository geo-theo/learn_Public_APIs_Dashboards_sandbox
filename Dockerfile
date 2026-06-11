FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data/raw
EXPOSE 8000

CMD ["python", "-m", "montana_data_lab", "serve", "--host", "0.0.0.0", "--port", "8000"]
