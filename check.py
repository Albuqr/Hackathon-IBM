import requests

print('STATS:', requests.get('http://localhost:8000/stats', timeout=30).json())
print()
events = requests.get('http://localhost:8000/events', timeout=30).json()
for e in events:
    sev = e['severity']
    tipo = e['crisis_type']
    pais = e['country']
    titulo = e['title'][:50]
    print(f"{sev}/5 | {tipo} | {pais} | {titulo}")