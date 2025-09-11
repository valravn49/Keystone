import os
from typing import Dict, Any
PROVIDER = os.getenv('LLM_PROVIDER','openai').lower()
MODEL = os.getenv('LLM_MODEL','gpt-4o-mini')
MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS','300'))
def _openai_chat(messages: list, **kwargs) -> str:
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=min(MAX_TOKENS, kwargs.get('max_tokens', MAX_TOKENS)),
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print('LLM error:', e)
        return ''
def generate_line(sister_name: str, persona_text: str, knobs: Dict[str, float], purpose: str, theme: str, rotation: Dict[str,Any], anchors: str, recent: str) -> str:
    system = (
        f'You are {sister_name}. Persona:\n{persona_text}\n\n'
        f'Style knobs (0..1): {knobs}\n'
        'Rules:\n'
        '- Keep it ≤ 200 words.\n'
        '- Respect privacy rule (only formal outfits & training gear are logged).\n'
        '- No explicit sexual content; keep tone consistent with persona.\n'
        '- Include the weekly theme name exactly once.\n'
    )
    user = (
        f'Purpose: {purpose}\n'
        f'Theme: {theme}\n'
        f'Rotation: lead={rotation.get(''lead'')}, rest={rotation.get(''rest'')}, supports={', '.join(rotation.get(''supports'', []))}\n'
        f'Anchors: {anchors}\n'
        f'Recent: {recent}\n'
        f'Write ONE chat message only.'
    )
    messages=[{'role':'system','content':system},{'role':'user','content':user}]
    if PROVIDER == 'openai':
        return _openai_chat(messages)
    return ''