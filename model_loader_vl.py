"""
model_loader_vl.py — Loads Qwen2.5-VL vision model.
Prefers local folder (Vera/model/Qwen2.5-VL-3B-Instruct/) over HuggingFace cache.
"""
import os
import torch
from pathlib import Path
from config import VL_MODEL_ID, VL_MODEL_LOCAL, VL_MAX_TOKENS, VL_MAX_IMAGE_SIZE

_model     = None
_processor = None


def get_model():
    global _model, _processor
    if _model is not None:
        return _model, _processor

    from transformers.models.qwen2_5_vl import Qwen2_5_VLForConditionalGeneration, Qwen2_5_VLProcessor
    from transformers import AutoProcessor, BitsAndBytesConfig

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    # Use local folder if it exists, otherwise fail with clear error
    # Check multiple possible locations
    possible_paths = [
        Path(VL_MODEL_LOCAL),
        Path(__file__).parent / "model" / "Qwen2.5-VL-3B-Instruct",
        Path("C:/Users/TEK/Desktop/Vera/model/Qwen2.5-VL-3B-Instruct"),
    ]

    model_source = None
    for p in possible_paths:
        if p.exists() and any(p.iterdir()):
            model_source = str(p)
            print(f"[VL] Loading from local folder: {model_source}")
            break

    if model_source is None:
        raise FileNotFoundError(
            f"VL model not found. Expected at: {VL_MODEL_LOCAL}\n"
            f"Make sure Qwen2.5-VL-3B-Instruct is in Vera/model/ folder."
        )
    local_only = True

    _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_source,
        quantization_config=bnb_config,
        device_map="cuda",
        torch_dtype=torch.float16,
        local_files_only=local_only,
    )
    _processor = AutoProcessor.from_pretrained(
        model_source,
        local_files_only=local_only,
    )
    return _model, _processor


def _resize_image(image_path: str) -> str:
    from PIL import Image
    import tempfile
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    if max(w, h) <= VL_MAX_IMAGE_SIZE:
        return image_path
    ratio = VL_MAX_IMAGE_SIZE / max(w, h)
    img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img.save(tmp.name, "JPEG", quality=95)
    return tmp.name


def chat_with_image(messages: list, image_path: str = None, max_tokens: int = VL_MAX_TOKENS) -> str:
    model, processor = get_model()
    from qwen_vl_utils import process_vision_info

    tmp_path = None
    if image_path and Path(image_path).exists():
        tmp_path = _resize_image(image_path)
        vl_messages = list(messages[:-1])
        last = messages[-1]
        vl_messages.append({
            "role": "user",
            "content": [
                {"type": "image", "image": tmp_path},
                {"type": "text",  "text": last["content"] + " Be honest if unsure."}
            ]
        })
    else:
        vl_messages = messages

    text = processor.apply_chat_template(vl_messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(vl_messages)
    inputs = processor(text=[text], images=image_inputs, videos=video_inputs,
                       padding=True, return_tensors="pt").to("cuda")

    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)

    generated = output_ids[:, inputs.input_ids.shape[1]:]
    result = processor.batch_decode(generated, skip_special_tokens=True,
                                    clean_up_tokenization_spaces=False)[0].strip()

    if tmp_path and tmp_path != image_path:
        try:
            os.unlink(tmp_path)
        except:
            pass

    return result


def chat(messages: list, max_tokens: int = VL_MAX_TOKENS, temperature: float = 0.7) -> str:
    return chat_with_image(messages, image_path=None, max_tokens=max_tokens)