# NewsReader Agent

The NewsReader agent is responsible for processing news content using vision-language models (LlaVA). It can analyze screenshots of news articles to extract text and structure when traditional text extraction fails.

## Key Features

- **Vision-based Extraction**: Uses `LlavaOnevisionForConditionalGeneration` to "read" news articles from images.
- **Lazy Loading**: The heavy LLaVA model is loaded *on demand* (first request) rather than at startup. This ensures the agent starts quickly and only consumes GPU memory when actually needed.
- **Processing Modes**:
    - `FAST`: Uses lightweight extraction (Trafilatura).
    - `PRECISE`: Uses vision model for high-accuracy extraction.
    - `BALANCED`: Tries fast first, falls back to vision if needed.

## Architecture

- **Engine**: `agents/newsreader/newsreader_engine.py` contains the core logic.
- **Service**: `agents/newsreader/main.py` exposes a FastAPI interface.
- **Tools**: `agents/newsreader/tools.py` provides utility functions.

## lazy Loading Behavior

To improve system startup time and resource usage, the LLaVA model is not initialized in the `__init__` method of `NewsReaderEngine`. Instead, `_ensure_llava_model_loaded()` is called before any operation that requires the model.

- **Startup**: Immediate (milliseconds). `is_llava_available()` checks environment potential, not loaded state.
- **First Request**: May take significant time (~10-30s depending on hardware) to load the model into GPU memory.
- **Subsequent Requests**: Fast inference.

## Configuration

Configuration is handled via `NewsReaderConfig` dataclass.

- `model_path`: Path to the LLaVA model.
- `processing_mode`: Default processing strategy.
- `device`: Target device (cuda/cpu).
