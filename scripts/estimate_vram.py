import sys

def gb(mb):
    return mb / 1024

def print_row(model, params, precision, weight_gb, kv_overhead_gb):
    total = weight_gb + kv_overhead_gb
    print(f"| {model:<25} | {params:<10} | {precision:<10} | {weight_gb:>8.2f} GB | {kv_overhead_gb:>8.2f} GB | {total:>8.2f} GB |")
    return total

def estimate_vram():
    print("\n=== VRAM ESTIMAION: RTX 3090 (24 GB) ===\n")
    print(f"| {'Model':<25} | {'Params':<10} | {'Precision':<10} | {'Weights':>11} | {'Context':>11} | {'Total':>11} |")
    print("|" + "-"*91 + "|")

    # 1. Mistral 7B (Current Config: BF16)
    # 7.2B params * 2 bytes = 14.4 GB
    mistral_bf16 = print_row("Mistral 7B v0.3 (Active)", "7.2B", "BF16", 14.4, 6.0)

    # 2. Qwen 2.5 14B (AWQ)
    # 14B params * 4 bits (0.5 bytes) + overhead ~ 0.6 bytes/param approx effective
    # Realistically AWQ files for 14B are ~9GB on disk.
    qwen_14b_awq = print_row("Qwen 2.5 14B", "14.7B", "AWQ (Int4)", 9.2, 4.0)

    # 3. Qwen VL 2B
    # 2B * 2 bytes = 4GB
    qwen_vl = print_row("Qwen2 VL 2B", "2B", "FP16", 4.2, 1.0)

    # 4. Whisper Large
    whisper = print_row("Whisper Large v3", "1.5B", "FP16", 3.1, 0.5)

    print("|" + "-"*91 + "|")

    # Scenarios
    print("\n--- SCENARIOS ---\n")
    
    # S1: "Everything" as currently configured
    s1_weights = 14.4 + 9.2 + 4.2 + 3.1
    s1_ctx = 6.0 # Shared context buffer if we squeeze, but realistically higher
    print(f"1. ALL LOADED (Current Config):")
    print(f"   Weights: {s1_weights:.2f} GB")
    print(f"   Min Context Buffer: {s1_ctx:.2f} GB")
    print(f"   Total Required:   {s1_weights + s1_ctx:.2f} GB")
    print(f"   Status:  ❌ EXCEEDS 24GB (Over by ~{(s1_weights + s1_ctx) - 24:.2f} GB)")

    print("\n2. SWAPPING STRATEGY (Sequential):")
    print(f"   Max Peak: {max(mistral_bf16, qwen_14b_awq, qwen_vl):.2f} GB (Mistral BF16)")
    print(f"   Status:   ✅ FITS (Comfortably)")

    print("\n3. OPTIMIZED STRATEGY (Quantize Mistral to Int4):")
    # If we shrink Mistral to AWQ
    mistral_awq_weight = 7.2 * 0.7 # Approx 5GB
    s3_weights = mistral_awq_weight + 9.2 + 4.2 + 3.1
    print(f"   Mistral (Int4): {mistral_awq_weight:.2f} GB")
    print(f"   Qwen 14B (Int4): 9.20 GB")
    print(f"   Others (FP16):   7.30 GB")
    print(f"   Total Weights:   {s3_weights:.2f} GB")
    print(f"   Remaining Ctx:   {24 - s3_weights:.2f} GB")
    print(f"   Status:          ⚠️  Possible but tight (<2.5GB for active context)")

if __name__ == "__main__":
    estimate_vram()
