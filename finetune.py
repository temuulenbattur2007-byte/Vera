"""
finetune.py — Fine-tune Vera on your own conversations.
Uses Unsloth for fast LoRA fine-tuning on Qwen2.5.

Run: python finetune.py
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOGS_DIR      = Path("logs")
OUTPUT_DIR    = Path("finetuned")
DATASET_FILE  = Path("finetune_dataset.jsonl")
BASE_MODEL    = "Qwen/Qwen2.5-7B-Instruct"  # HuggingFace base model ID
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Step 1: Convert logs to training data ─────────────────────────────────────
def build_dataset():
    """
    Read all daily logs and convert them to ChatML training format.
    Each user+Vera exchange becomes one training sample.
    """
    from persona import SYSTEM_PROMPT

    samples = []
    log_files = sorted(LOGS_DIR.glob("*.json"))

    if not log_files:
        print("[Finetune] No logs found in logs/ folder. Talk to Vera first!")
        return 0

    print(f"[Finetune] Found {len(log_files)} day(s) of logs...")

    for log_file in log_files:
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            messages = data.get("messages", [])

            # Group into user/assistant pairs
            pairs = []
            i = 0
            while i < len(messages):
                if messages[i]["role"] == "user":
                    user_msg = messages[i]["content"]
                    if i + 1 < len(messages) and messages[i+1]["role"] == "assistant":
                        assistant_msg = messages[i+1]["content"]
                        pairs.append((user_msg, assistant_msg))
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1

            # Build training samples with sliding context window
            for j, (user_msg, assistant_msg) in enumerate(pairs):
                # Include up to 3 previous exchanges as context
                context = []
                for k in range(max(0, j-3), j):
                    context.append({"role": "user",      "content": pairs[k][0]})
                    context.append({"role": "assistant", "content": pairs[k][1]})

                sample = {
                    "messages": [
                        {"role": "system",    "content": SYSTEM_PROMPT},
                        *context,
                        {"role": "user",      "content": user_msg},
                        {"role": "assistant", "content": assistant_msg},
                    ]
                }
                samples.append(sample)

        except Exception as e:
            print(f"[Finetune] Skipping {log_file.name}: {e}")

    if not samples:
        print("[Finetune] No valid conversation pairs found.")
        return 0

    # Write dataset
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"[Finetune] Dataset built: {len(samples)} training samples → {DATASET_FILE}")
    return len(samples)


# ── Step 2: Fine-tune with Unsloth ───────────────────────────────────────────
def finetune(num_samples):
    print("\n[Finetune] Loading Unsloth + model...")
    print("[Finetune] This will take a while on first run (downloading base model).\n")

    try:
        from unsloth import FastLanguageModel
        from datasets import Dataset
        from trl import SFTTrainer
        from transformers import TrainingArguments
        import torch
    except ImportError as e:
        print(f"[Finetune] Missing dependency: {e}")
        print("Install with: pip install unsloth datasets trl transformers torch")
        return

    # Load base model with Unsloth (4-bit quantized for speed)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=2048,
        dtype=None,           # Auto-detect
        load_in_4bit=True,    # 4-bit for memory efficiency
    )

    # Add LoRA adapters — only train a small part of the model
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,                 # LoRA rank — higher = more capacity but slower
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # Load dataset
    print("[Finetune] Loading dataset...")
    raw_data = []
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        for line in f:
            raw_data.append(json.loads(line))

    def format_sample(sample):
        """Convert messages to ChatML string format."""
        text = ""
        for msg in sample["messages"]:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                text += f"<|im_start|>system\n{content}<|im_end|>\n"
            elif role == "user":
                text += f"<|im_start|>user\n{content}<|im_end|>\n"
            elif role == "assistant":
                text += f"<|im_start|>assistant\n{content}<|im_end|>\n"
        return {"text": text}

    formatted = [format_sample(s) for s in raw_data]
    dataset = Dataset.from_list(formatted)

    print(f"[Finetune] Training on {len(dataset)} samples...")

    # Training config — conservative for a laptop GPU
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        num_train_epochs=3,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        save_steps=50,
        save_total_limit=2,
        report_to="none",       # No wandb
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=2048,
        dataset_num_proc=2,
        args=training_args,
    )

    print("[Finetune] Starting training...\n")
    trainer.train()

    # Save LoRA adapter
    adapter_path = OUTPUT_DIR / "vera_lora"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    print(f"\n[Finetune] LoRA adapter saved to: {adapter_path}")

    # Export merged GGUF for llama-cpp-python
    print("\n[Finetune] Exporting merged model to GGUF...")
    _export_gguf(model, tokenizer)


def _export_gguf(model, tokenizer):
    """Merge LoRA and export as GGUF for use with llama-cpp-python."""
    try:
        merged_path = OUTPUT_DIR / "vera_merged"
        model.save_pretrained_merged(
            str(merged_path),
            tokenizer,
            save_method="merged_16bit",
        )
        print(f"[Finetune] Merged model saved to: {merged_path}")

        # Convert to GGUF
        gguf_path = OUTPUT_DIR / "vera_finetuned_q6.gguf"
        model.save_pretrained_gguf(
            str(OUTPUT_DIR / "vera_finetuned"),
            tokenizer,
            quantization_method="q6_k",
        )
        print(f"\n[Finetune] ✅ GGUF exported!")
        print(f"[Finetune] Update model_loader.py to point to:")
        print(f"  {OUTPUT_DIR / 'vera_finetuned_q6.gguf'}")
        print(f"\n[Finetune] Vera has learned from your conversations!")

    except Exception as e:
        print(f"[Finetune] GGUF export failed: {e}")
        print("[Finetune] You can still use the LoRA adapter with transformers.")


# ── Step 3: Schedule automatic retraining ────────────────────────────────────
def schedule_info():
    print("""
[Finetune] To retrain Vera automatically:

Option A — Run manually whenever you want:
    python finetune.py

Option B — Schedule weekly (Windows Task Scheduler):
    1. Open Task Scheduler
    2. Create Basic Task → Weekly
    3. Action: Start a program
    4. Program: C:\\Users\\TEK\\Desktop\\Vera\\venv\\Scripts\\python.exe
    5. Arguments: C:\\Users\\TEK\\Desktop\\Vera\\finetune.py
    6. Start in: C:\\Users\\TEK\\Desktop\\Vera

The more you talk to Vera, the better she gets.
""")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  Vera Fine-Tuning Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\n[Step 1] Building dataset from your conversations...")
    n = build_dataset()

    if n == 0:
        print("\nNo data to train on yet. Talk to Vera more first!")
        sys.exit(0)

    if n < 10:
        print(f"\nOnly {n} samples — ideally have 50+ before fine-tuning.")
        answer = input("Continue anyway? (yes/no): ").strip().lower()
        if answer != "yes":
            sys.exit(0)

    print(f"\n[Step 2] Fine-tuning on {n} samples...")
    print("Warning: This will use your GPU and take 10-60 minutes depending on data size.")
    answer = input("Start fine-tuning? (yes/no): ").strip().lower()

    if answer == "yes":
        finetune(n)
        schedule_info()
    else:
        print(f"\nDataset saved to {DATASET_FILE} — run again when ready.")