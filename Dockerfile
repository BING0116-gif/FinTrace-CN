FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FINTRACE_CACHE_DIR=/app/data/.cache

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt && \
    useradd --create-home --uid 10001 fintrace

COPY src/ src/
COPY scripts/ scripts/
COPY api.py workbench.py ./
COPY .streamlit/ .streamlit/

RUN mkdir -p /app/data /app/output && chown -R fintrace:fintrace /app
USER fintrace

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)" || exit 1

CMD ["sh", "-c", "python scripts/bootstrap_demo.py && python -m streamlit run workbench.py --server.address=0.0.0.0 --server.port=8501"]
