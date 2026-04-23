import subprocess
import sys

python = sys.executable
orchestrate = python.replace("python.exe", "orchestrate.exe")

tools = [
    "tools/fetch_gdacs.py",
    "tools/fetch_reliefweb.py",
    "tools/fetch_usgs.py",
    "tools/classify_crisis.py",
    "tools/save_classification.py",
    "tools/match_volunteers.py",
    "tools/notify_telegram.py",
    "tools/notify_whatsapp.py",
    "tools/analyze_distribution.py",
    "tools/suggest_reallocation.py",
]

agents = [
    "agents/monitoring_agent.yaml",
    "agents/classification_agent.yaml",
    "agents/matching_agent.yaml",
    "agents/communication_agent.yaml",
    "agents/optimization_agent.yaml",
    "agents/crisis_orchestrator.yaml",
]

print("=" * 50)
print("IMPORTANDO TOOLS...")
print("=" * 50)
for tool in tools:
    print(f"\n>> {tool}")
    result = subprocess.run(
        [orchestrate, "tools", "import", "-k", "python", "-f", tool],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"   OK")
    else:
        print(f"   ERRO: {result.stderr or result.stdout}")

print("\n" + "=" * 50)
print("IMPORTANDO AGENTES...")
print("=" * 50)
for agent in agents:
    print(f"\n>> {agent}")
    result = subprocess.run(
        [orchestrate, "agents", "import", "-f", agent],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"   OK")
    else:
        print(f"   ERRO: {result.stderr or result.stdout}")

print("\n" + "=" * 50)
print("FAZENDO DEPLOY DO SUPERVISOR...")
print("=" * 50)
result = subprocess.run(
    [orchestrate, "agents", "deploy", "--name", "crisis_orchestrator"],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("   Deploy OK!")
else:
    print(f"   ERRO: {result.stderr or result.stdout}")

print("\n" + "=" * 50)
print("VERIFICANDO AGENTES...")
print("=" * 50)
result = subprocess.run(
    [orchestrate, "agents", "list", "-v"],
    capture_output=True, text=True
)
print(result.stdout)
print("CONCLUIDO!")