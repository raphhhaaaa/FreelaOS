import os
import json
import time
import logging
from google import genai
from openai import OpenAI

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY") ## roteamento de modelos gratuitos pela nvidia vim
# CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") # Placeholder para futura implementação nativa

_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
_groq_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1", timeout=25.0) if GROQ_API_KEY else None
_openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=25.0) if OPENAI_API_KEY else None
_nvidia_client = OpenAI(api_key=NVIDIA_API_KEY, base_url="https://integrate.api.nvidia.com/v1", timeout=25.0) if NVIDIA_API_KEY else None

def _call_provider(prompt: str, provedor: str, force_json: bool = False) -> str:
    """Função interna para chamar o provedor específico."""
    if provedor == "groq":
        if not _groq_client: raise ValueError("GROQ_API_KEY não configurada no ambiente.")
        res = _groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if force_json else None,
            max_tokens=4096
        )
        return res.choices[0].message.content
        
    elif provedor == "openai":
        if not _openai_client: raise ValueError("OPENAI_API_KEY não configurada no ambiente.")
        res = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if force_json else None
        )
        return res.choices[0].message.content
        
    elif provedor == "nvidia":
        if not _nvidia_client: raise ValueError("NVIDIA_API_KEY não configurada no ambiente.")
        res = _nvidia_client.chat.completions.create(
            model="deepseek-ai/deepseek-v4-flash-0731",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if force_json else None,
            max_tokens=4096
        )
        return res.choices[0].message.content

    elif provedor == "openrouter":
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_api_key: raise ValueError("OPENROUTER_API_KEY não configurada no ambiente.")
        openrouter_client = OpenAI(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1", timeout=25.0)
        res = openrouter_client.chat.completions.create(
            model="dots-studio/dots-3-note-preview:free",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if force_json else None
        )
        return res.choices[0].message.content
    elif provedor == "gemini-lite":
        if not _gemini_client: raise ValueError("GEMINI_API_KEY não configurada no ambiente.")
        config = {'response_mime_type': 'application/json'} if force_json else None
        res = _gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt, 
            config=config
        )
        return res.text
        
    else:
        # Default é Gemini
        if not _gemini_client: raise ValueError("GEMINI_API_KEY não configurada no ambiente.")
        config = {'response_mime_type': 'application/json'} if force_json else None
        
        try:
            # Tenta usar o 3.5-flash primeiro
            res = _gemini_client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt, 
                config=config
            )
            return res.text
        except Exception as e:
            logger.warning(f"[GEMINI INTERNAL FALLBACK] gemini-3.5-flash falhou ({e}). Tentando gemini-3.1-flash-lite...")
            res = _gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt, 
                config=config
            )
            return res.text

def _get_active_llm(user_id: str) -> str:
    from backend.src.modules.opportunities.repository import ProfileRepository
    profile_repo = ProfileRepository()
    config = profile_repo.get_user_settings(user_id)
    if config and config.get("integracoes"):
        integracoes = config["integracoes"]
        for llm in ["groq", "openai", "claude", "gemini", "nvidia"]:
            val = integracoes.get(llm)
            if isinstance(val, dict) and val.get("enabled") is True:
                return llm
            elif val is True:
                return llm
    return "gemini"

def generate_text(prompt: str, provedor: str = "gemini-lite", max_retries: int = 3) -> str:
    """
    Chama a IA solicitando texto puro.
    Fallback Universal: Se Gemini falhar, tenta Groq. Se qualquer outro falhar, tenta Gemini.
    """
    fallback_provedor = "groq" if provedor == "gemini" else "gemini"
    
    for attempt in range(max_retries):
        try:
            return _call_provider(prompt, provedor, force_json=False)
        except Exception as api_err:
            if attempt < max_retries - 1:
                wait_time = 5 * (attempt + 1)
                logger.warning(f"[LLM RETRY] Provedor {provedor} falhou ({api_err}). Tentando novamente em {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"[LLM FALLBACK] Provedor {provedor} falhou {max_retries} vezes. Acionando fallback {fallback_provedor}...")
                try:
                    return _call_provider(prompt, fallback_provedor, force_json=False)
                except Exception as fallback_err:
                    logger.error(f"[LLM ERROR] Ambos os provedores falharam. Erro: {fallback_err}")
                    raise Exception(f"Ambos os modelos falharam. Erro final: {fallback_err}")

def generate_json(prompt: str, provedor: str = "gemini-lite", max_retries: int = 3, force_json: bool = True) -> dict:
    """
    Chama a IA solicitando JSON.
    Fallback Universal: Se Gemini falhar, tenta Groq. Se qualquer outro falhar, tenta Gemini.
    """
    fallback_provedor = "groq" if provedor == "gemini" else "gemini"
    
    texto_resposta = None
    for attempt in range(max_retries):
        try:
            texto_resposta = _call_provider(prompt, provedor, force_json=force_json)
            break
        except Exception as api_err:
            if attempt < max_retries - 1:
                wait_time = 5 * (attempt + 1)
                logger.warning(f"[LLM RETRY] Provedor {provedor} falhou ({api_err}). Tentando novamente em {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"[LLM FALLBACK] Provedor {provedor} falhou {max_retries} vezes. Acionando fallback {fallback_provedor}...")
                try:
                    texto_resposta = _call_provider(prompt, fallback_provedor, force_json=force_json)
                    break
                except Exception as fallback_err:
                    logger.error(f"[LLM ERROR] Ambos os provedores falharam. Erro: {fallback_err}")
                    raise Exception(f"Ambos os modelos falharam. Erro final: {fallback_err}")
                    
    if not texto_resposta:
        raise ValueError("Resposta vazia retornada pelo LLM.")
    clean_json = texto_resposta.replace("```json", "").replace("```", "").strip()
    
    # Previne quebra se o modelo esquecer a primeira chave
    if not clean_json.startswith("{") and "{" in clean_json:
        clean_json = clean_json[clean_json.find("{"):]
        
    try:
        import json_repair
        # Usa json_repair para consertar má formatação agressiva (como strings multilinhas, aspas soltas, vírgulas faltando)
        obj = json_repair.repair_json(clean_json, return_objects=True)
        if obj:
            logger.info(f"[LLM JSON] Utilizado provedor: {provedor}")
            return obj
        raise ValueError("O JSON retornado estava completamente destruído e não pôde ser salvo.")
    except Exception as e:
        logger.error(f"Erro ao parsear JSON do LLM com json_repair: {clean_json}")
        raise ValueError(f"LLM não retornou um JSON válido. Erro: {str(e)}")
