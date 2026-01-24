import re

# Read the file
with open('monitoring/core/trace_collector.py', 'r') as f:
    content = f.read()

# Replace the JustNewsMetrics initialization
content = content.replace(
    'self.metrics = JustNewsMetrics()',
    'self.metrics = JustNewsMetrics(self.agent_name)'
)

# Replace the histogram method call
content = re.sub(
    r'self\.collection_latency = self\.metrics\.create_histogram\(\s*"trace_collection_latency_seconds",\s*"Time spent collecting traces",\s*\[\"operation\"\],\s*\)',
    'self.collection_latency = self.metrics._get_or_create_histogram("trace_collection_latency_seconds")',
    content
)

# Replace the span_count counter method call
content = re.sub(
    r'self\.span_count = self\.metrics\.create_counter\(\s*"trace_spans_total",\s*"Total number of spans collected",\s*\[\"service", "status"\],\s*\)',
    'self.span_count = self.metrics._get_or_create_counter("trace_spans_total")',
    content
)

# Replace the trace_count counter method call
content = re.sub(
    r'self\.trace_count = self\.metrics\.create_counter\(\s*"traces_total",\s*"Total number of traces processed",\s*\[\"status\"\],\s*\)',
    'self.trace_count = self.metrics._get_or_create_counter("traces_total")',
    content
)

# Write the file back
with open('monitoring/core/trace_collector.py', 'w') as f:
    f.write(content)

print('TraceCollector code has been fixed')
