import requests
import xml.etree.ElementTree as ET

print("=" * 50)
print("TESTANDO GDACS (corrigido)...")
print("=" * 50)
try:
    r = requests.get(
        "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
        params={"eventlist": "EQ;TC;FL;VO;DR;WF", "alertlevel": "orange;red"},
        headers={"User-Agent": "hktn26-crisis-monitor/1.0"},
        timeout=15
    )
    print(f"Status: {r.status_code}")
    # Remover BOM e caracteres invalidos
    content = r.content
    if content.startswith(b'\xef\xbb\xbf'):
        content = content[3:]
    content = content.decode('utf-8', errors='ignore').encode('utf-8')
    root = ET.fromstring(content)
    items = root.findall(".//item")
    print(f"Itens encontrados: {len(items)}")
    for item in items[:5]:
        print(f"  - {item.findtext('title','')}")
except Exception as e:
    print(f"ERRO: {e}")

print()
print("=" * 50)
print("TESTANDO RELIEFWEB (corrigido)...")
print("=" * 50)
try:
    r = requests.get(
        "https://api.reliefweb.int/v2/disasters",
        params={
            "appname": "hktn26-crisis-monitor",
            "filter[field]": "status",
            "filter[value]": "current",
            "limit": 10,
            "sort[]": "date:desc",
            "fields[include][]": ["name", "country", "type", "date"]
        },
        headers={
            "User-Agent": "hktn26-crisis-monitor/1.0",
            "Accept": "application/json"
        },
        timeout=15
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Total: {data.get('totalCount', 0)}")
        for d in data.get("data", [])[:5]:
            print(f"  - {d['fields'].get('name','')}")
    else:
        print(f"Resposta: {r.text[:200]}")
except Exception as e:
    print(f"ERRO: {e}")

print()
print("=" * 50)
print("TESTANDO EONET (alternativa ao ReliefWeb)...")
print("=" * 50)
try:
    r = requests.get(
        "https://eonet.gsfc.nasa.gov/api/v3/events",
        params={"status": "open", "limit": 10},
        timeout=15
    )
    print(f"Status: {r.status_code}")
    events = r.json().get("events", [])
    print(f"Eventos: {len(events)}")
    for e in events[:5]:
        print(f"  - {e.get('title','')} | {e.get('categories',[{}])[0].get('title','')}")
except Exception as e:
    print(f"ERRO: {e}")