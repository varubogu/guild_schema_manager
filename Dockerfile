FROM python:3.12-slim

RUN useradd -m botuser
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir uv && \
    uv pip install --system .

USER botuser
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "bot"]
