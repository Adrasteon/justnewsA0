
def print_row(model, params, precision, weight_gb, kv_overhead_gb):
    total = weight_gb + kv_overhead_gb
    print(f"| {model:<25} | {params:<10} | {precision:<10} | {weight_gb:>8.2f} GB | {kv_overhead_gb:>8.2f} GB | {total:>8.2f} GB |")
    return weight_gb, kv_overhead_gb

def estimate_vram():
    print("\n=== VRAM ESTIMATION: RTX 3090 (24 GB) -- NEW CONFIG ===\n")
    print(f"| {'Model':<25} | {'Params':<10} | {'Precision':<10} | {'Weights':>11} | {'Context':>11} | {'Total':>11} |")
    print("|" + "-"*91 + "|")

    # 1. Qwen 2.5 14B (Primary - Active)
    qwen_14b_w, qwen_14b_ctx = print_row("Qwen 2.5 14B (Active)", "14.7B", "AWQ (Int4)", 9.2, 5.5)
    # Note on context: 14B model needs decent KV cache. 4.0 was conservative. 5.5 is safer for long docs.

    # 2. Qwen VL 2B (Vision)
    qwen_vl_w, qwen_vl_ctx = print_row("Qwen2 VL 2B", "2B", "FP16", 4.2, 1.0)

    # 3. Whisper Large (Audio)
    whisper_w, whisper_ctx = print_row("Whisper Large v3", "1.5B", "FP16", 3.1, 0.5)

    print("|" + "-"*91 + "|")

    # Scenarios
    print("\n--- SCENARIOS ---\n")

    # S1: All Concurent
    total_weights = qwen_14b_w + qwen_vl_w + whisper_w
    # If running concurrently, we need context for all.
    # Though usually we don't infer on all 3 millisecond-simultaneously, they strictly occupy VRAM.
    total_ctx = qwen_14b_ctx + qwen_vl_ctx + whisper_ctx

    grand_total = total_weights + total_ctx

    print("1. TOTAL CONCURRENT LOAD (All Models in VRAM):")
    print(f"   Total Weights:   {total_weights:.2f} GB")
    print(f"   Combined Ctx:    {total_ctx:.2f} GB")
    print(f"   Grand Total:     {grand_total:.2f} GB")
    print("   Available:       24.00 GB")
    print(f"   Headroom:        {24.00 - grand_total:.2f} GB")

    if grand_total < 24.0:
        print("   Status:          ✅ FITS (Simultaneous Residency Possible!)")
    else:
        print("   Status:          ❌ OOM (Overflow)")

    print("\n2. REALISTIC WORKFLOW (Audio/Vision separate from Reasoning):")
    # Usually we TRANSCRIBE (Whisper) -> then ANALYZE (Qwen). We don't need Whisper in memory during Qwen.
    # We might need VL + Qwen simultaneously for multi-modal analysis if not using the VL for everything.

    peak_workflow = qwen_14b_w + qwen_14b_ctx + qwen_vl_w + qwen_vl_ctx # Only Reasoning + Vision
    print(f"   Reasoning + Vision: {peak_workflow:.2f} GB")
    print("   Status:             ✅ FITS EASILY")

if __name__ == "__main__":
    estimate_vram()
