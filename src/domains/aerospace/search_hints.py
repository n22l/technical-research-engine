"""Optional aerospace discovery vocabulary; never an evidence assessment."""
def search_hint(text):
    if any(word in text.lower() for word in ('booster', 'reuse', 'reflight', '复飞', '重复使用')):
        return ' booster reflight mission'
    return ''
