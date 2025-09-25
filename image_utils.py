# image_utils.py
import base64
import io
from openai import AsyncOpenAI
from logger import log_event

client = AsyncOpenAI()

async def generate_image(prompt: str, size: str = "1024x1024", n: int = 1):
    """
    Generate an image from a text prompt.
    Returns a list of in-memory file-like objects (BytesIO).
    """
    try:
        response = await client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            n=n,
            response_format="b64_json",
        )
        results = []
        for item in response.data:
            b64 = item.b64_json
            img_bytes = base64.b64decode(b64)
            results.append(io.BytesIO(img_bytes))
        return results
    except Exception as e:
        log_event(f"[ERROR] Image generation failed: {e}")
        return []
