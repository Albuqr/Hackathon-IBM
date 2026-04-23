import requests

print('STATS:', requests.get('http://localhost:8000/stats').json())
print()
events = requests.get('http://localhost:8000/events').json()
for e in events:
    sev = e['severity']
    tipo = e['crisis_type']
    pais = e['country']
    titulo = e['title'][:50]
    print(f"{sev}/5 | {tipo} | {pais} | {titulo}")