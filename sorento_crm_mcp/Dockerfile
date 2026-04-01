FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY sorento_crm_mcp ./sorento_crm_mcp
RUN pip install --no-cache-dir -e .

ENV CRM_MCP_HOST=0.0.0.0
ENV CRM_MCP_PORT=8765

EXPOSE 8765

CMD ["python", "-m", "sorento_crm_mcp"]
