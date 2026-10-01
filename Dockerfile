FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN pip install -r requirements.lock
COPY crm_agent ./crm_agent
COPY dashboard ./dashboard
COPY config ./config
RUN pip install --no-deps . && useradd --create-home portfolio && mkdir -p data && chown portfolio:portfolio data
USER portfolio
EXPOSE 8000 8501
CMD ["python", "-m", "uvicorn", "crm_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
