import re
import sys
from collections import Counter


def tokenize(text):
    return re.findall(r"[a-zA-Z']+", text.lower())


def sentences(text):
    return [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s]


def word_counter(words):
    return Counter(words)


def top_n(counter, n=10):
    return counter.most_common(n)


def avg_word_length(words):
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)


def avg_sentence_length(sents):
    if not sents:
        return 0.0
    return sum(len(tokenize(s)) for s in sents) / len(sents)


def flesch_score(words, sents):
    if not words or not sents:
        return 0.0
    asl = avg_sentence_length(sents)
    asw = avg_word_length(words) / 3.0
    return 206.835 - 1.015 * asl - 84.6 * asw


def hapax_words(counter):
    return [word for word, count in counter.items() if count == 1]


def type_token_ratio(words):
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def compute_stats(text):
    tokens = tokenize(text)
    sents = sentences(text)
    counter = word_counter(tokens)
    return {
        'total_words': len(tokens),
        'unique_words': len(set(tokens)),
        'total_sentences': len(sents),
        'avg_word_length': round(avg_word_length(tokens), 2),
        'avg_sentence_length': round(avg_sentence_length(sents), 2),
        'flesch_score': round(flesch_score(tokens, sents), 2),
        'type_token_ratio': round(type_token_ratio(tokens), 2),
        'hapax_count': len(hapax_words(counter)),
        'top_10_words': top_n(counter, 10),
    }


def print_stats(stats):
    print(f"Total words        : {stats['total_words']}")
    print(f"Unique words       : {stats['unique_words']}")
    print(f"Total sentences    : {stats['total_sentences']}")
    print(f"Avg word length    : {stats['avg_word_length']}")
    print(f"Avg sentence length: {stats['avg_sentence_length']} words")
    print(f"Flesch score       : {stats['flesch_score']}")
    print(f"Type-token ratio   : {stats['type_token_ratio']}")
    print(f"Hapax legomena     : {stats['hapax_count']}")
    print("Top 10 words:")
    for word, count in stats['top_10_words']:
        print(f"  {word:<20} {count}")


SAMPLE_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "A fox is a cunning animal. Dogs are loyal companions. "
    "The dog barked at the fox. The fox ran away quickly. "
    "Both animals live in the wild. The wild is their home. "
    "Home is where the heart is. The heart of a fox is brave. "
    "Brave animals survive in the wild."
)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    else:
        text = SAMPLE_TEXT
    stats = compute_stats(text)
    print_stats(stats)
