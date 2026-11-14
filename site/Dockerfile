# ushka.satela.com.br: built by the Satela agent with the repository root as
# context (dockerfile: site/Dockerfile, contexto: .).
#
# The site runs on Ushka installed from this very repository, and the docs are
# rendered at startup by ushka.docs from ../docs (API reference from ../src).
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /repo
COPY pyproject.toml README.md LICENSE ./
COPY src src
RUN pip install --no-cache-dir ".[docs]"
COPY docs docs
COPY site site
RUN useradd --system --uid 10001 ushka && chown -R ushka /repo
USER ushka
WORKDIR /repo/site
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz').status != 200)"
CMD ["ushka", "run", "app:app"]
