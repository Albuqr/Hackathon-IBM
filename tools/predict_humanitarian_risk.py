import os
import json
from ibm_watsonx_ai import Credentials, APIClient
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GP
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_client = None


def _get_model():
    global _client
    if not _client:
        api = APIClient(
            Credentials(
                url="https://us-south.ml.cloud.ibm.com",
                api_key=os.environ["WATSONX_APIKEY"]
            ),
            project_id=os.environ["WATSONX_PROJECT_ID"]
        )
        _client = ModelInference(
            model_id="ibm/granite-3-3-8b-instruct",
            api_client=api,
            params={
                GP.DECODING_METHOD: "greedy",
                GP.MAX_NEW_TOKENS: 1200,
                GP.TEMPERATURE: 0,
                GP.STOP_SEQUENCES: ["```"]
            }
        )
    return _client


@tool
def predict_humanitarian_risk(events_json: str) -> str:
    """Analisa eventos recentes de crise e prediz riscos humanitários futuros usando Granite.

    Args:
        events_json: JSON string com lista de eventos recentes do banco de dados.
                     Cada evento deve ter: id, title, country, lat, lon, severity,
                     crisis_type, urgency, source.
    Returns:
        JSON string com lista de predições, cada uma com: location, country, lat, lon,
        risk_type, probability, estimated_timeframe, recommended_preemptive_action,
        estimated_affected_population.
    """
    try:
        events = json.loads(events_json)
    except Exception:
        return json.dumps({"error": "events_json inválido", "predictions": []})

    if not events:
        return json.dumps({"predictions": [], "note": "Nenhum evento para analisar"})

    # Resumir eventos para o prompt (evitar tokens excessivos)
    summary_lines = []
    for ev in events[:50]:
        summary_lines.append(
            f"- [{ev.get('crisis_type','?')}] {ev.get('title','?')} "
            f"| País: {ev.get('country','?')} | Sev: {ev.get('severity','?')} "
            f"| Urgência: {ev.get('urgency','?')} | Fonte: {ev.get('source','?')}"
        )
    events_summary = "\n".join(summary_lines)

    prompt = f"""Você é um analista de inteligência humanitária sênior da ONU.
Analise os eventos de crise abaixo e identifique quais têm maior risco de ESCALAR
para crises humanitárias maiores nos próximos 7 a 30 dias.

EVENTOS RECENTES:
{events_summary}

Foque em:
1. Tempestades tropicais ou furacões se formando perto de costas populosas
2. Zonas sísmicas ativas com potencial de grandes réplicas
3. Regiões de seca próximas a populações com insegurança alimentar
4. Conflitos mostrando sinais de escalada (aumento de frequência, novos atores)
5. Surtos de doenças em regiões com saúde pública frágil

Retorne APENAS um JSON válido com esta estrutura exata:
```json
{{
  "predictions": [
    {{
      "location": "Nome da região ou cidade específica",
      "country": "Nome do país em português",
      "lat": 0.0,
      "lon": 0.0,
      "risk_type": "tipo do risco (meteorological/seismic/conflict/drought/humanitarian/sanitary)",
      "probability": "low|medium|high",
      "estimated_timeframe": "7 dias|14 dias|30 dias",
      "recommended_preemptive_action": "Ação específica recomendada em português",
      "estimated_affected_population": 0,
      "justification": "Explicação de 1-2 frases em português"
    }}
  ],
  "analysis_timestamp": "ISO datetime",
  "total_events_analyzed": {len(events)}
}}
```"""

    try:
        result = _get_model().generate_text(prompt=prompt).strip()
        # Strip markdown code fence if present
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        result = result.strip().rstrip("```").strip()
        parsed = json.loads(result)
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": f"Granite retornou JSON inválido: {str(e)}",
            "raw": result[:500] if 'result' in dir() else "",
            "predictions": []
        })
    except Exception as e:
        return json.dumps({"error": str(e), "predictions": []})
