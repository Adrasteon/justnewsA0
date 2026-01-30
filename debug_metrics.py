from common.metrics import JustNewsMetrics
from prometheus_client import generate_latest

def test_metrics_output():
    # Initialize metrics for a test agent
    m = JustNewsMetrics("test_agent")
    
    # Generate output WITHOUT setting values
    output_before = generate_latest(m.registry).decode('utf-8')
    print("--- BEFORE SETTING VALUES ---")
    # print(output_before)
    if "justnews_processing_queue_size" in output_before:
        lines = [l for l in output_before.split('\n') if "justnews_processing_queue_size" in l]
        print("Queue Size Metric Lines (Before):")
        for l in lines: print(l)
    else:
        print("Queue Size Metric: MISSING")

    # Set a value
    m.processing_queue_size.labels(
        agent="test_agent", 
        agent_display_name=m.display_name,
        queue_type="main",
        queue_display_name="Main Queue"
    ).set(0)

    output_after = generate_latest(m.registry).decode('utf-8')
    print("\n--- AFTER SETTING VALUES ---")
    if "justnews_processing_queue_size" in output_after:
        lines = [l for l in output_after.split('\n') if "justnews_processing_queue_size" in l]
        print("Queue Size Metric Lines (After):")
        for l in lines: print(l)
    else:
        print("Queue Size Metric: MISSING")

if __name__ == "__main__":
    test_metrics_output()
