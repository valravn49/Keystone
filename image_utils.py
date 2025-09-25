# image_utils.py
import os
from openai import OpenAI
from logger import log_event

# Create a client (reads API key from OPENAI_API_KEY env var)
client = OpenAI()

def generate_image(prompt: str, size: str = "1024x1024"):
    """
    Generate an image from a text prompt using OpenAI's image model.
    Returns the image URL.
    """
    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
        )
        url = result.data[0].url
        log_event(f"[IMAGE_GEN] Prompt: {prompt} → {url}")
        return url
    except Exception as e:
        log_event(f"[ERROR] Image generation failed: {e}")
        return None


async def maybe_generate_image_request(message: str, sister: str, config: dict):
    """
    Lightweight hook: decide if a message is a request for an image.
    If yes, generate and return the image URL.
    """
    keywords = ["draw", "sketch", "image", "render", "outfit", "picture"]
    lowered = message.lower()

    if any(kw in lowered for kw in keywords):
        # Default to 1024x1024 unless overridden
        size = "1024x1024"
        url = generate_image(f"{sister} request: {message}", size=size)
        if url:
            return f"{sister} generated an image for: \"{message}\"\n{url}"
    return None
