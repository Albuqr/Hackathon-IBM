import json, sys
s, out = sys.argv[1], sys.argv[2]
g = json.load(open(f'{s}/mun-minima.json')); p = json.load(open(f'{s}/popmun.json'))
muns = {str(m['id']): m for m in json.load(open(f'{s}/muns.json'))}
ufg = json.load(open(f'{s}/br-uf.json')); ufs = {str(x['id']): x for x in json.load(open(f'{s}/ufs.json'))}
var = {}
for v in p:
    var[v['id']] = {}
    for r in v['resultados'][0]['series']:
        try: var[v['id']][r['localidade']['id']] = float(r['serie']['2022'])
        except (ValueError, TypeError): pass
def rnd(c, k=3):
    return [rnd(x, k) for x in c] if isinstance(c[0], list) else [round(c[0], k), round(c[1], k)]
feats, faltam = [], []
for f in g['features']:
    cod = f['properties']['codarea']; m = muns.get(cod)
    if not m or cod not in var['93'] or cod not in var['614']: faltam.append(cod); continue
    uf = m['regiao-imediata']['regiao-intermediaria']['UF']
    feats.append({"type": "Feature", "properties": {
        "id": int(cod), "nome": m['nome'], "uf": uf['sigla'], "regiao": uf['regiao']['nome'],
        "pop_2022": var['93'][cod], "area_km2": var['6318'][cod], "densidade_2022": var['614'][cod]},
        "geometry": {"type": f['geometry']['type'], "coordinates": rnd(f['geometry']['coordinates'])}})
estados = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"sigla": ufs[f['properties']['codarea']]['sigla']},
    "geometry": {"type": f['geometry']['type'], "coordinates": rnd(f['geometry']['coordinates'])}} for f in ufg['features']]}
dados = {"fonte": "IBGE — Censo 2022 (tabela 4714), malhas municipais e estaduais (API de malhas v3)",
         "geojson": {"type": "FeatureCollection", "features": feats}, "estados": estados}
open(out, 'w').write("/* gerado de dados do IBGE: troque pelos seus indicadores mantendo a estrutura */\nwindow.DADOS = " + json.dumps(dados, ensure_ascii=False, separators=(',', ':')) + ";\n")
print(len(g['features']), 'malha;', len(feats), 'ok; faltam', faltam[:10])
