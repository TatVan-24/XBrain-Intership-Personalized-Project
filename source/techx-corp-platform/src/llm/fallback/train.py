"""LoRA fine-tuning entry point tuned for a 4 GB laptop GPU."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="google-t5/t5-small")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--max-input-tokens", type=int, default=256)
    parser.add_argument("--max-target-tokens", type=int, default=96)
    args = parser.parse_args()

    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from transformers import DataCollatorForSeq2Seq, Seq2SeqTrainer, Seq2SeqTrainingArguments
    except ImportError as error:
        raise SystemExit("Install requirements-train.txt before training") from error

    files = {}
    for split in ("train", "validation", "test"):
        path = args.data_dir / f"{split}.jsonl"
        if path.exists() and path.stat().st_size > 0:
            files[split] = str(path)
    if "train" not in files:
        raise SystemExit("The prepared dataset has no training examples")

    dataset = load_dataset("json", data_files=files)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model)
    model.gradient_checkpointing_enable()
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q", "v"],
    ))

    def tokenize(batch):
        inputs = tokenizer(batch["input_text"], truncation=True, max_length=args.max_input_tokens)
        labels = tokenizer(text_target=batch["target_text"], truncation=True, max_length=args.max_target_tokens)
        inputs["labels"] = labels["input_ids"]
        return inputs

    tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset["train"].column_names)
    has_validation = "validation" in tokenized
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=16,
        learning_rate=2e-4,
        warmup_ratio=0.05,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if has_validation else "no",
        save_total_limit=2,
        predict_with_generate=True,
        report_to="none",
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized.get("validation"),
        data_collator=DataCollatorForSeq2Seq(tokenizer, model=model),
        processing_class=tokenizer,
    )
    trainer.train()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    (args.output_dir / "training_manifest.json").write_text(json.dumps({
        "base_model": args.model,
        "method": "lora",
        "max_input_tokens": args.max_input_tokens,
        "max_target_tokens": args.max_target_tokens,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
