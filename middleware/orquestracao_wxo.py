"""Cliente do watsonx Orchestrate (get_wxo_token/call_orchestrate), movido de middleware/main.py.

O núcleo (/ingest, /chat, /predictions) não usa mais este módulo. Ele permanece só porque o provedor
`watsonx` do módulo Brasil (middleware/brasil/orquestracao/watsonx.py) importa `call_orchestrate` de
middleware.main (re-exportado lá). Variáveis: WO_API_KEY, WO_INSTANCE, ORCHESTRATOR_AGENT_ID.
Candidato a remoção quando o Brasil deixar de oferecer o provedor watsonx.
"""
import os
import time

import requests

# ── Token cache ──
_token_cache = {"token": None, "exp": 0}

def get_wxo_token():
    if _token_cache["token"] and time.time() < _token_cache["exp"] - 60:
        return _token_cache["token"]
    r = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey",
              "apikey": os.environ["WO_API_KEY"]}, timeout=30
    )
    r.raise_for_status()
    d = r.json()
    _token_cache["token"] = d["access_token"]
    _token_cache["exp"] = time.time() + d["expires_in"]
    return _token_cache["token"]

def call_orchestrate(message: str, agent_id: str = None, max_wait: int = 120) -> dict:
    base = os.environ["WO_INSTANCE"]
    token = get_wxo_token()
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    aid = agent_id or os.environ["ORCHESTRATOR_AGENT_ID"]
    r = requests.post(
        f"{base}/v1/orchestrate/runs?stream=false",
        headers=headers,
        json={"message": {"role": "user", "content": message},
              "agent_id": aid},
        timeout=120
    )
    r.raise_for_status()
    data = r.json()
    run_id = data.get("run_id")

    interval   = 5
    iterations = max_wait // interval
    print(f"[orchestrate] run_id={run_id} | timeout={max_wait}s | polling every {interval}s (max {iterations} attempts)")

    start = time.time()
    for attempt in range(1, iterations + 1):
        time.sleep(interval)
        elapsed = time.time() - start
        r2 = requests.get(
            f"{base}/v1/orchestrate/runs/{run_id}",
            headers=headers, timeout=30
        )
        if r2.status_code == 200:
            run_data = r2.json()
            status   = run_data.get("status", "unknown")
            print(f"[orchestrate] attempt {attempt}/{iterations} | status={status} | elapsed={elapsed:.1f}s")
            if status == "completed":
                try:
                    content = run_data.get("result", {}).get("data", {}).get("message", {}).get("content", "")
                    if isinstance(content, list):
                        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    print(f"[orchestrate] COMPLETED | run_id={run_id} | response: {str(content)[:500]}")
                except Exception as _le:
                    print(f"[orchestrate] COMPLETED | run_id={run_id} | (could not parse response: {_le})")
                return run_data
            elif status == "failed":
                return {"error": run_data.get("last_error")}
        else:
            print(f"[orchestrate] attempt {attempt}/{iterations} | poll HTTP {r2.status_code} | elapsed={elapsed:.1f}s")

    print(f"[orchestrate] TIMEOUT after {time.time() - start:.1f}s (limit={max_wait}s) | run_id={run_id}")
    return {"error": "timeout"}
