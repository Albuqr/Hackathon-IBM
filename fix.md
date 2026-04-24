# Crisis Monitor — Docker Deploy Files

Read all project files before starting. Create the following files.

---

## Dockerfile.middleware

For the FastAPI middleware service (port 8000):
- Base image: python:3.12-slim
- Working directory: /app
- Copy middleware/, tools/, agents/, data/, .env
- Install dependencies from middleware/requirements.txt
- Expose port 8000
- CMD: uvicorn middleware.main:app --host 0.0.0.0 --port 8000

## Dockerfile.frontend

For the Flask frontend service (port 5000):
- Base image: python:3.12-slim
- Working directory: /app
- Copy frontend/, data/, .env
- Install from frontend/requirements.txt
- Expose port 5000
- CMD: python frontend/app.py

## docker-compose.yml

Services:
- middleware: builds Dockerfile.middleware, port 8000:8000, volume ./data:/app/data, env_file .env, restart always
- frontend: builds Dockerfile.frontend, port 5000:5000, volume ./data:/app/data, env_file .env, environment API_URL=http://middleware:8000, depends_on middleware, restart always

Both services on a bridge network called crisis-net.
No Traefik labels needed — the VPS uses Easypanel which handles routing separately.

## requirements files

Create middleware/requirements.txt if missing:
  fastapi
  uvicorn[standard]
  python-dotenv
  requests
  httpx
  ibm-watsonx-orchestrate==2.8.0
  python-telegram-bot
  pydantic

Create frontend/requirements.txt if missing:
  flask
  python-dotenv
  requests

## .dockerignore

Create at project root:
  .venv
  __pycache__
  *.pyc
  .git
  fix.md