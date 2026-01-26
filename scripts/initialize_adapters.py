#!/usr/bin/env python3
"""
Initialize empty LoRA adapters for all agents in AGENT_MODEL_MAP.json.
This solves the cold-start problem where agents expect adapters to exist before they can be trained.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if basedir not in sys.path:
    sys.path.insert(0, basedir)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import get_peft_model, LoraConfig, TaskType
from agents.common.model_store import ModelStore
import logging
# from common.observability import get_logger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_adapters")

def main():
    # Load Agent Model Map
    project_root = Path(__file__).resolve().parent.parent
    # Handle the fact that we might be in scripts/ or project root
    if not (project_root / "AGENT_MODEL_MAP.json").exists():
        project_root = Path(__file__).resolve().parent.parent # /home/adra/justnewsA0

    model_map_path = project_root / "AGENT_MODEL_MAP.json"
    if not model_map_path.exists():
        logger.error(f"Could not find AGENT_MODEL_MAP.json at {model_map_path}")
        sys.exit(1)

    with open(model_map_path) as f:
        model_map = json.load(f)

    # We assume all agents currently share the same base model (Mistral 7B)
    # in the 'agents' section. We'll load it once.
    base_model_ref = "mistral-7b-v0.3" 
    # Verify this base ref is used
    
    logger.info(f"Loading base model: {base_model_ref}...")
    # In a real scenario, use specific path from base_models section, 
    # but for initialization we can often rely on HF cache or model store.
    # Here we assume standard HF ID for simplicity of initialization script, 
    # or we could parse the model store path if strictly required.
    base_model_id = model_map["base_models"][base_model_ref]["hf_id"]
    
    # Init ModelStore
    model_store_root = Path(os.environ.get("MODEL_STORE_ROOT", project_root / "model_store"))
    store = ModelStore(model_store_root)

    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    tokenizer.pad_token = tokenizer.eos_token

    # Load model in 4bit or 8bit to save memory during init if possible, or just fp16
    # effectively we just need to initialize the weights.
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="auto"
    )

    # Standard Config for our Agents
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        inference_mode=False, # We want to be able to train these
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]
    )

    agents = model_map.get("agents", {})
    
    for agent_name, variants in agents.items():
        if not isinstance(variants, list):
            variants = [variants]
            
        for variant in variants:
            if variant.get("base_ref") != base_model_ref:
                logger.warning(f"Skipping {agent_name} (base_ref mismatch or not supported yet)")
                continue
                
            adapter_name = variant["adapter_name"]
            # Construct the relative path expected by the system
            # AGENT_MODEL_MAP says: "adapter_model_store_path": "synthesizer/adapters/mistral_synth_v1"
            # ModelStore expects: root / agent / versions / version
            
            # We treat the adapter_name as the 'version' for the model store in this context?
            # Or does the system expect a specific structure?
            # Looking at AGENT_MODEL_MAP: "adapter_model_store_path": "synthesizer/adapters/mistral_synth_v1"
            
            # It seems the config path is a relative path inside the model store.
            # Let's clean it up.
            
            target_path_rel = variant["adapter_model_store_path"]
            # e.g. synthesizer/adapters/mistral_synth_v1
            
            # We want to use the ModelStore API to "stage" and "finalize" this.
            # The ModelStore usually does root/agent/versions/version
            # But here the map defines a deeper structure. 
            # Let's write directly to the path defined to ensure it matches exactly what the loader expects.
            
            full_output_path = model_store_root / target_path_rel
            
            if full_output_path.exists():
                logger.info(f"Adapter for {agent_name} already exists at {full_output_path}, skipping.")
                continue

            logger.info(f"Initializing adapter for {agent_name} at {full_output_path}")
            
            # Create a PEFT model
            peft_model = get_peft_model(model, lora_config)
            
            # Save it
            peft_model.save_pretrained(full_output_path)
            logger.info(f"Saved {adapter_name}")

    logger.info("All adapters initialized.")

if __name__ == "__main__":
    main()
