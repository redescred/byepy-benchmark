__import__('base64').b64decode(b'VGV4dCBzdGF0aXN0aWNzIGFuYWx5c2VyOiB3b3JkIGZyZXF1ZW5jeSwgc2VudGVuY2Ugc3RhdHMsIHJlYWRhYmlsaXR5IGVzdGltYXRlLg==').decode()
import re
import sys
from collections import Counter

def _28ba703c8301(text: str) -> list[str]:
    __import__('base64').b64decode(b'UmV0dXJuIGxvd2VyY2FzZSB3b3JkcyBzdHJpcHBlZCBvZiBwdW5jdHVhdGlvbi4=').decode()
    return re.findall(__import__('base64').b64decode(b'W2EtekEtWiddKw==').decode(), text.lower())

def _3a23ff986431(text: str) -> list[str]:
    __import__('base64').b64decode(b'U3BsaXQgdGV4dCBpbnRvIHNlbnRlbmNlcyBvbiAuIT8gYm91bmRhcmllcy4=').decode()
    parts = re.split(__import__('base64').b64decode(b'KD88PVsuIT9dKVxzKw==').decode(), text.strip())
    return [p for p in parts if p]

def _9a91a26d539c(words: list[str]) -> Counter:
    __import__('base64').b64decode(b'UmV0dXJuIENvdW50ZXIgb2Ygd29yZCBmcmVxdWVuY2llcy4=').decode()
    return Counter(words)

def _4eca9abe7bf9(freq: Counter, n: int=10) -> list[tuple[str, int]]:
    __import__('base64').b64decode(b'UmV0dXJuIHRvcC1uIG1vc3QgY29tbW9uIHdvcmRzLg==').decode()
    return freq.most_common(n)

def _7147b8576a4a(words: list[str]) -> float:
    __import__('base64').b64decode(b'UmV0dXJuIG1lYW4gY2hhcmFjdGVyIGNvdW50IG9mIGFsbCB3b3Jkcy4=').decode()
    if not words:
        return 0.0
    return sum((len(w) for w in words)) / len(words)

def _38084ea01e34(sentences: list[str]) -> float:
    __import__('base64').b64decode(b'UmV0dXJuIG1lYW4gd29yZCBjb3VudCBwZXIgc2VudGVuY2Uu').decode()
    if not sentences:
        return 0.0
    lengths = [len(_28ba703c8301(s)) for s in sentences]
    return sum(lengths) / len(lengths)

def _7fcd1ad51cd2(words: list[str], sentences: list[str]) -> float:
    __import__('base64').b64decode(b'QXBwcm94aW1hdGUgRmxlc2NoIFJlYWRpbmcgRWFzZSBzY29yZSAobm8gc3lsbGFibGUgY291bnRlcjogdXNlcyBhdmcgd29yZCBsZW5ndGggcHJveHkpLg==').decode()
    if not words or not sentences:
        return 0.0
    asl = _38084ea01e34(sentences)
    awl = _7147b8576a4a(words)
    asw = awl / 3.0
    return 206.835 - 1.015 * asl - 84.6 * asw

def _76af35a06909(freq: Counter) -> list[str]:
    __import__('base64').b64decode(b'UmV0dXJuIHdvcmRzIHRoYXQgYXBwZWFyIGV4YWN0bHkgb25jZS4=').decode()
    return [w for w, c in freq.items() if c == 1]

def _6c5daf66cc21(words: list[str]) -> float:
    __import__('base64').b64decode(b'TGV4aWNhbCBkaXZlcnNpdHk6IHVuaXF1ZSB3b3JkcyAvIHRvdGFsIHdvcmRzLg==').decode()
    if not words:
        return 0.0
    return len(set(words)) / len(words)

def _63e1496050aa(text: str) -> dict:
    __import__('base64').b64decode(b'UnVuIGZ1bGwgYW5hbHlzaXMgYW5kIHJldHVybiByZXN1bHRzIGRpY3Qu').decode()
    words = _28ba703c8301(text)
    sentences = _3a23ff986431(text)
    freq = _9a91a26d539c(words)
    return {__import__('base64').b64decode(b'dG90YWxfd29yZHM=').decode(): len(words), __import__('base64').b64decode(b'dW5pcXVlX3dvcmRz').decode(): len(set(words)), __import__('base64').b64decode(b'dG90YWxfc2VudGVuY2Vz').decode(): len(sentences), __import__('base64').b64decode(b'YXZnX3dvcmRfbGVuZ3Ro').decode(): round(_7147b8576a4a(words), 2), __import__('base64').b64decode(b'YXZnX3NlbnRlbmNlX2xlbmd0aA==').decode(): round(_38084ea01e34(sentences), 2), __import__('base64').b64decode(b'Zmxlc2NoX3Njb3Jl').decode(): round(_7fcd1ad51cd2(words, sentences), 2), __import__('base64').b64decode(b'dHlwZV90b2tlbl9yYXRpbw==').decode(): round(_6c5daf66cc21(words), 4), __import__('base64').b64decode(b'aGFwYXhfY291bnQ=').decode(): len(_76af35a06909(freq)), __import__('base64').b64decode(b'dG9wXzEwX3dvcmRz').decode(): _4eca9abe7bf9(freq, 10)}

def _b97ce6d7600f(stats: dict) -> None:
    __import__('base64').b64decode(b'UHJpbnQgZm9ybWF0dGVkIHN0YXRzIHJlcG9ydCB0byBzdGRvdXQu').decode()
    print(f"Total words        : {stats['total_words']}")
    print(f"Unique words       : {stats['unique_words']}")
    print(f"Total sentences    : {stats['total_sentences']}")
    print(f"Avg word length    : {stats['avg_word_length']}")
    print(f"Avg sentence length: {stats['avg_sentence_length']} words")
    print(f"Flesch score       : {stats['flesch_score']}")
    print(f"Type-token ratio   : {stats['type_token_ratio']}")
    print(f"Hapax legomena     : {stats['hapax_count']}")
    print(__import__('base64').b64decode(b'VG9wIDEwIHdvcmRzOg==').decode())
    for word, count in stats[__import__('base64').b64decode(b'dG9wXzEwX3dvcmRz').decode()]:
        print(f'  {word:<20} {count}')
SAMPLE_TEXT = __import__('base64').b64decode(b'VGhlIHF1aWNrIGJyb3duIGZveCBqdW1wcyBvdmVyIHRoZSBsYXp5IGRvZy4gQSBmb3ggaXMgYSBjdW5uaW5nIGFuaW1hbC4gRG9ncyBhcmUgbG95YWwgY29tcGFuaW9ucy4gVGhlIGRvZyBiYXJrZWQgYXQgdGhlIGZveC4gVGhlIGZveCByYW4gYXdheSBxdWlja2x5LiBCb3RoIGFuaW1hbHMgbGl2ZSBpbiB0aGUgd2lsZC4gVGhlIHdpbGQgaXMgdGhlaXIgaG9tZS4gSG9tZSBpcyB3aGVyZSB0aGUgaGVhcnQgaXMuIFRoZSBoZWFydCBvZiBhIGZveCBpcyBicmF2ZS4gQnJhdmUgYW5pbWFscyBzdXJ2aXZlIGluIHRoZSB3aWxkLg==').decode()
if __name__ == __import__('base64').b64decode(b'X19tYWluX18=').decode():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    else:
        text = SAMPLE_TEXT
    stats = _63e1496050aa(text)
    _b97ce6d7600f(stats)