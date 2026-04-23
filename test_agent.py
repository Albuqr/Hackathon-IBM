import os
import json
import requests
import time

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

def get_token():
    r = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": os.environ["WO_API_KEY"]
        }
    )
    return r.json()["access_token"]

def test_agent(message: str):
    token = get_token()
    base = os.environ['WO_INSTANCE']
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Enviar mensagem
    print(f"Enviando: {message}")
    r = requests.post(
        f"{base}/v1/orchestrate/runs?stream=false",
        headers=headers,
        json={
            "message": {"role": "user", "content": message},
            "agent_id": os.environ["ORCHESTRATOR_AGENT_ID"]
        },
        timeout=120
    )
    data = r.json()
    run_id = data.get("run_id")
    thread_id = data.get("thread_id")
    print(f"Run ID: {run_id} | Status: aguardando...")

    # Aguardar conclusão pelo run_id
    for i in range(24):
        time.sleep(5)
        r2 = requests.get(
            f"{base}/v1/orchestrate/runs/{run_id}",
            headers=headers
        )
        if r2.status_code == 200:
            run_data = r2.json()
            status = run_data.get("status")
            print(f"  [{i+1}/24] Status: {status}")

            if status == "completed":
                # Resposta está em result.data.message
                try:
                    msg = run_data["result"]["data"]["message"]
                    content = msg.get("content", "")
                    print(f"\n Resposta do agente:\n{content}")
                except Exception:
                    print("\nResposta completa:")
                    print(json.dumps(run_data.get("result"), indent=2, ensure_ascii=False))
                return

            elif status == "failed":
                print(f"\n Falhou: {run_data.get('last_error')}")
                return

    # Buscar mensagens do thread como fallback
    print("\nBuscando no thread...")
    r3 = requests.get(
        f"{base}/v1/orchestrate/threads/{thread_id}/messages",
        headers=headers
    )
    if r3.status_code == 200:
        msgs = r3.json()
        for msg in reversed(msgs):
            if msg.get("role") == "assistant":
                print(f"\n Resposta:\n{msg.get('content','')}")
                return
    print("Timeout sem resposta.")

if __name__ == "__main__":
    test_agent("Quais crises estao ativas no momento? Faca uma coleta rapida.")