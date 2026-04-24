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
        JSON string com lista de predições, cada uma com: location, country,
        risk_type, probability, timeframe, recommended_action.
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

    prompt = f"""You are a humanitarian intelligence analyst. Based on these active crisis events, identify which situations are most likely to escalate into larger humanitarian emergencies in the next 7 to 30 days. For each prediction, explain the reasoning and suggest preemptive actions. Return your analysis as a JSON array.

ACTIVE CRISIS EVENTS:
{events_summary}

Focus on:
1. Tropical storms or hurricanes forming near populated coasts
2. Active seismic zones with potential for major aftershocks
3. Drought regions near populations with food insecurity
4. Conflicts showing escalation signs (increasing frequency, new actors)
5. Disease outbreaks in regions with fragile public health

Return ONLY valid JSON with this exact structure:
```json
{{
  "predictions": [
    {{
      "location": "specific region or city name",
      "country": "country name in Portuguese",
      "risk_type": "meteorological|seismic|conflict|drought|humanitarian|sanitary",
      "probability": "low|medium|high",
      "timeframe": "7 days|14 days|30 days",
      "recommended_action": "specific preemptive action in Portuguese",
      "justification": "1-2 sentence explanation in Portuguese"
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
