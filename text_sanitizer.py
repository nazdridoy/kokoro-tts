import re

def sanitize_text(text):
    # Replace non-breaking space (\xa0) with a full stop (.)
    text = text.replace('\xa0', '.')

    text = text.replace('i. e.', 'i.e.')

    text = re.sub(r'e\.\s*g\.(\s*,)?', 'for example', text)

    # Remove number (1 or 2 digits) that appears right after a full stop. They are usually citations
    text = re.sub(r'\.\s*\d{1,2}(?=\D)', '', text)

    return text