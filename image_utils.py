from image_gen import text2im

async def generate_character_image(character: str, prompt: str, size="1024x1024"):
    """
    Generate an image based on a sibling's prompt.
    """
    try:
        result = await text2im({
            "prompt": f"{character} concept art, {prompt}",
            "size": size,
            "n": 1
        })
        if result and "data" in result and len(result["data"]) > 0:
            return result["data"][0]["url"]
    except Exception as e:
        return f"[ERROR] Image generation failed for {character}: {e}"
