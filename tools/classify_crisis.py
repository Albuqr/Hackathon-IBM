import os
import json
from ibm_watsonx_ai import Credentials, APIClient
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GP
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_client = None


def _get_classifier():
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
                GP.MAX_NEW_TOKENS: 150,
                GP.TEMPERATURE: 0,
                GP.STOP_SEQUENCES: ["\n\n"]
            }
        )
    return _client


@tool
def classify_crisis(event_json: str) -> str:
    """Classifica severidade, urgencia e tipo de uma crise usando Granite.

    Args:
        event_json: JSON string do evento a ser classificado contendo
                    pelo menos title, type e country.
    Returns:
        JSON string com severity(1-5), urgency, type, confidence e justification.
    """
    event = json.loads(event_json)
    title = event.get("title", "")
    country = event.get("country", "")
    etype = event.get("type", "")
    affected = event.get("people_affected", 0)

    prompt = f"""Classifique a crise abaixo. Responda APENAS com JSON valido, sem texto adicional.

Escala de severidade:
1=baixo(<100 afetados), 2=medio-baixo(100-1000), 3=medio(1000-10000), 4=alto(10000-100000), 5=critico(>100000)

Urgencia: immediate(risco de vida ativo), 24h(agravando rapido), 48h(intervencao necessaria), 7days(planejamento), monitoring(acompanhar)

Tipo: meteorological, seismic, humanitarian, political, sanitary, wildfire, drought

Exemplos:
Evento: "Earthquake M7.2 Turkey 2000 deaths" -> {{"severity":5,"urgency":"immediate","type":"seismic","confidence":0.97,"justification":"Terremoto de alta magnitude com vitimas confirmadas"}}
Evento: "Flooding in south Brazil 500 displaced" -> {{"severity":3,"urgency":"24h","type":"meteorological","confidence":0.91,"justification":"Enchente com deslocamento significativo de populacao"}}
Evento: "Minor drought Kenya monitoring" -> {{"severity":2,"urgency":"monitoring","type":"drought","confidence":0.85,"justification":"Seca moderada sem impacto imediato critico"}}
Evento: "Cholera outbreak DRC 10000 cases" -> {{"severity":4,"urgency":"immediate","type":"sanitary","confidence":0.94,"justification":"Surto epidemico de grande escala requer resposta urgente"}}

Evento: "{title} - {country} - tipo:{etype} - afetados:{affected}"
Resposta:"""

    try:
        result = _get_classifier().generate_text(prompt=prompt).strip()
        # Garantir que e JSON valido
        parsed = json.loads(result)
        # Adicionar campos obrigatorios se ausentes
        parsed.setdefault("confidence", 0.8)
        parsed.setdefault("justification", "Classificacao automatica")
        parsed.setdefault("trend", "stable")
        parsed.setdefault("needs_review", parsed.get("confidence", 1) < 0.7)
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        # Fallback se Granite nao retornar JSON valido
        fallback = {
            "severity": 2,
            "urgency": "monitoring",
            "type": etype or "humanitarian",
            "confidence": 0.5,
            "justification": "Classificacao de fallback - revisar manualmente",
            "needs_review": True,
            "trend": "stable"
        }
        return json.dumps(fallback, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "needs_review": True})