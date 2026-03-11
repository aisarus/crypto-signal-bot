FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
RUN mkdir -p data
RUN useradd -m bot && chown -R bot:bot /app
USER bot
CMD ["python", "-m", "src.main"]
