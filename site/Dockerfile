# ushka.satela.com.br: built by the Satela agent with the repository root as
# context (dockerfile: site/Dockerfile, contexto: .).

# --- docs: build the MkDocs site for /docs/ -----------------------------------
FROM python:3.14-slim AS docs
WORKDIR /src
COPY site/requirements-docs.txt site/requirements-docs.txt
RUN pip install --no-cache-dir -r site/requirements-docs.txt
COPY mkdocs.yml ./
COPY docs docs
COPY overrides overrides
COPY src src
ENV USHKA_DOCS_URL=https://ushka.satela.com.br/docs/ \
    USHKA_DOCS_OPTIMIZE=false
RUN mkdocs build --strict -d /out/docs

# --- runtime: the site, served by Ushka from this very repository -------------
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/ushka
COPY pyproject.toml README.md LICENSE ./
COPY src src
RUN pip install --no-cache-dir . && rm -rf /opt/ushka/src
WORKDIR /app
COPY site/ ./
COPY --from=docs /out/docs public/docs
RUN useradd --system --uid 10001 ushka && chown -R ushka /app
USER ushka
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz').status != 200)"
CMD ["ushka", "run", "app:app"]
