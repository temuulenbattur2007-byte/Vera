"""
model_loader.py — Loads the main text model via llama-cpp-python.
"""
import os
import sys
from pathlib import Path
from llama_cpp import Llama
from config import MODEL_PATH, GPU_LAYERS, CTX_SIZE, TEMPERATURE, MAX_TOKENS

_model = None

def get_model() -> Llama:
    global _model
    if _model is not None:
        return _model

    path = Path(MODEL_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Model not found: {path}\n"
            f"Update MODEL_PATH in config.py"
        )

    devnull = open(os.devnull, 'w')
    old_stderr = sys.stderr
    sys.stderr = devnull
    try:
        _model = Llama(
            model_path=str(path),
            n_ctx=CTX_SIZE,
            n_gpu_layers=GPU_LAYERS,
            verbose=False,
            chat_format="chatml",
        )
    finally:
        sys.stderr = old_stderr
        devnull.close()

    return _model


def chat(messages: list, max_tokens: int = MAX_TOKENS, temperature: float = TEMPERATURE) -> str:
    model = get_model()
    devnull = open(os.devnull, 'w')
    old_stderr = sys.stderr
    sys.stderr = devnull
    try:
        response = model.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<|im_end|>", "<|endoftext|>"],
        )
    finally:
        sys.stderr = old_stderr
        devnull.close()
    return response["choices"][0]["message"]["content"].strip()