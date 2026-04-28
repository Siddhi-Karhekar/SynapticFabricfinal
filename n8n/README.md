# n8n Agent Pipeline (Synaptic Fabric)

This folder ships the n8n workflow that drives the closed-loop
predictive-maintenance agent.

## Pipeline shape

```
FastAPI (alert)  --POST-->  n8n /webhook/synfab-alert
                                 |
                                 v
                         Normalize -> Switch on severity
                          /                       \
                  CRITICAL                       WARNING
                     |                              |
              Ollama (phi3) - cite manual         (skip LLM)
                     |                              |
                     v                              v
        POST /agent/action  (FastAPI)   POST /agent/action (FastAPI)
            action=AUTO_MAINTENANCE          action=NOTIFY_OPERATOR
```

## How to import

1. `docker compose up -d n8n qdrant ollama`
2. open http://localhost:5678 in a browser
3. on first launch n8n asks you to create a local owner account
   (no internet sign-up needed - this is the free Community Edition)
4. **Workflows -> Import from file** -> pick
   `n8n/workflows/synaptic_fabric_agent.json`
5. Open the workflow, click **Activate** in the top-right
6. Pull a small LLM into Ollama once:
   `docker exec -it synfab_ollama ollama pull phi3`

The workflow registers a webhook at
`http://localhost:5678/webhook/synfab-alert` which the FastAPI
backend posts to (`backend_fastapi/app/n8n_client.py`).
