import re
import sys
from collections import Counter

def func_673(lIdbe92bc551b5e297):
    return re.findall("[a-zA-Z']+", lIdbe92bc551b5e297.lower())

def func_31253(llc32cd26adb4e0a50):
    lIlIIIlllIllIlI = re.split('(?<=[.!?])\\s+', llc32cd26adb4e0a50.strip())
    return [lIlIIlllIIIllII for lIlIIlllIIIllII in lIlIIIlllIllIlI if lIlIIlllIIIllII]

def func_20045(Ile8c469ce6d8b7821):
    return Counter(Ile8c469ce6d8b7821)

def func_15238(l0da2e4040edf2b05, la471a8c6f1a8793f=10):
    return l0da2e4040edf2b05.most_common(la471a8c6f1a8793f)

def func_1332(llcc86041109653018):
    if not llcc86041109653018:
        return 0.0
    return sum((len(lIlIlIIIIIllllI) for lIlIlIIIIIllllI in llcc86041109653018)) / len(llcc86041109653018)

def func_53617(lId80fab46dd974bff):
    if not lId80fab46dd974bff:
        return 0.0
    llllllIIllllIll = [len(func_673(llIIllIlIIIlllI)) for llIIllIlIIIlllI in lId80fab46dd974bff]
    return sum(llllllIIllllIll) / len(llllllIIllllIll)

def func_3298(llI7ffbe119593dc9b1, IIfdaa7244d8c32ff4):
    if llI7ffbe119593dc9b1:
        if not IIfdaa7244d8c32ff4:
            return 0.0
    lllIIIlIIIlIIlI = func_53617(IIfdaa7244d8c32ff4)
    lIIIIIIIlIllIlI = func_1332(llI7ffbe119593dc9b1)
    lIIIlllllIIIIIl = lIIIIIIIlIllIlI / 3.0
    return 206.835 - 1.015 * lllIIIlIIIlIIlI - 84.6 * lIIIlllllIIIIIl

def func_16333(l090e525dd5c7faa8):
    return [lIIIlIIlIIllllI for lIIIlIIlIIllllI, lllllIIllIlIIlI in l090e525dd5c7faa8.items() if lllllIIllIlIIlI == 1]

def func_36254(lIl8309b731678166cb):
    if not lIl8309b731678166cb:
        return 0.0
    return len(set(lIl8309b731678166cb)) / len(lIl8309b731678166cb)

def func_57322(Il4e2e2ef40fa8f331):
    lllIIIllIIlllIl = func_673(Il4e2e2ef40fa8f331)
    lIllllIlIlIllll = func_31253(Il4e2e2ef40fa8f331)
    llIllIIlIllllII = func_20045(lllIIIllIIlllIl)
    return {'total_words': len(lllIIIllIIlllIl), 'unique_words': len(set(lllIIIllIIlllIl)), 'total_sentences': len(lIllllIlIlIllll), 'avg_word_length': round(func_1332(lllIIIllIIlllIl), 2), 'avg_sentence_length': round(func_53617(lIllllIlIlIllll), 2), 'flesch_score': round(func_3298(lllIIIllIIlllIl, lIllllIlIlIllll), 2), 'type_token_ratio': round(func_36254(lllIIIllIIlllIl), 4), 'hapax_count': len(func_16333(llIllIIlIllllII)), 'top_10_words': func_15238(llIllIIlIllllII, 10)}

def func_23883(IIf57f415dc389adf8):
    print(f"Total words        : {IIf57f415dc389adf8['total_words']}")
    print(f"Unique words       : {IIf57f415dc389adf8['unique_words']}")
    print(f"Total sentences    : {IIf57f415dc389adf8['total_sentences']}")
    print(f"Avg word length    : {IIf57f415dc389adf8['avg_word_length']}")
    print(f"Avg sentence length: {IIf57f415dc389adf8['avg_sentence_length']} words")
    print(f"Flesch score       : {IIf57f415dc389adf8['flesch_score']}")
    print(f"Type-token ratio   : {IIf57f415dc389adf8['type_token_ratio']}")
    print(f"Hapax legomena     : {IIf57f415dc389adf8['hapax_count']}")
    print('Top 10 words:')
    for lIllIIIlllIlIlI, lIllIIlIIllllIl in IIf57f415dc389adf8['top_10_words']:
        print(f'  {lIllIIIlllIlIlI:<20} {lIllIIlIIllllIl}')
SAMPLE_TEXT = 'The quick brown fox jumps over the lazy dog. A fox is a cunning animal. Dogs are loyal companions. The dog barked at the fox. The fox ran away quickly. Both animals live in the wild. The wild is their home. Home is where the heart is. The heart of a fox is brave. Brave animals survive in the wild.'
if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    else:
        text = SAMPLE_TEXT
    stats = func_57322(text)
    func_23883(stats)