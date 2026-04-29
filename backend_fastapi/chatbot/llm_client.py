# ==========================================
# LLM CLIENT (local Ollama, streaming-first)
# ==========================================

import ollama


MODEL_NAME = "phi3:mini"

# Default system prompt — chatbot_api passes its own context-rich prompt as
# the user message, so this stays neutral.
DEFAULT_SYSTEM_PROMPT = (
    "You are an industrial AI assistant for a 4-stage manufacturing line. "
    "Answer in plain English, 1-3 short sentences. Use only the data given. "
    "Be direct, helpful, and avoid jargon dumps."
)

# Token budget — old value (40) truncated answers mid-sentence.
DEFAULT_NUM_PREDICT = 100
DEFAULT_TEMPERATURE = 0.1
DEFAULT_NUM_CTX = 1024  # smaller context window = faster inference on CPU


def _options(num_predict=None, temperature=None):
    return {
        "num_predict": num_predict or DEFAULT_NUM_PREDICT,
        "temperature": DEFAULT_TEMPERATURE if temperature is None else temperature,
        "top_p": 0.9,
        "num_ctx": DEFAULT_NUM_CTX,
        "num_thread": 8,
    }


def warmup():
    """Pre-load model into memory so first user query isn't extra-slow."""
    try:
        ollama.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": "ok"}],
            options={"num_predict": 1, "num_ctx": 256},
        )
        print("[chatbot] model warmed:", MODEL_NAME)
    except Exception as e:
        print("[chatbot] warmup failed:", e)


def generate_llm_response(prompt: str, system_prompt: str = None, num_predict: int = None) -> str:
    """Blocking single-shot response. Used by /chat fallback."""
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            options=_options(num_predict=num_predict),
        )
        return response.get("message", {}).get("content", "").strip() or \
            "No response generated."
    except Exception as e:
        print("LLM ERROR:", e)
        return "AI temporarily unavailable. Live system data is still streaming."


def generate_llm_stream(prompt: str, system_prompt: str = None, num_predict: int = None):
    """Token stream. Used by /chat/stream."""
    try:
        stream = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            options=_options(num_predict=num_predict),
        )

        for chunk in stream:
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                yield piece

    except Exception as e:
        print("STREAM ERROR:", e)
        yield "AI stream interrupted."
