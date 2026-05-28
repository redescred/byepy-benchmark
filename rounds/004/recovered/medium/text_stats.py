import re
import sys
from collections import Counter


def tokenize(text):
    return re.findall(r"[a-zA-Z']+", text.lower())


def split_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s]


def word_counts(words):
    return Counter(words)


def top_words(counter, n=10):
    return counter.most_common(n)


def avg_word_length(words):
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)


def avg_sentence_length(sentences):
    if not sentences:
        return 0.0
    word_counts_per_sentence = [len(tokenize(s)) for s in sentences]
    return sum(word_counts_per_sentence) / len(word_counts_per_sentence)


def flesch_score(words, sentences):
    if not words or not sentences:
        return 0.0
    avg_sent_len = avg_sentence_length(sentences)
    avg_syllables = avg_word_length(words) / 3.0
    return 206.835 - 1.015 * avg_sent_len - 84.6 * avg_syllables


def hapax_legomena(counter):
    return [word for word, count in counter.items() if count == 1]


def type_token_ratio(words):
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def analyze_text(text):
    sentences = split_sentences(text)
    words = tokenize(text)
    counter = word_counts(words)
    return {
        'total_words': len(words),
        'unique_words': len(set(words)),
        'total_sentences': len(sentences),
        'avg_word_length': round(avg_word_length(words), 2),
        'avg_sentence_length': round(avg_sentence_length(sentences), 2),
        'flesch_score': round(flesch_score(words, sentences), 2),
        'type_token_ratio': round(type_token_ratio(words), 4),
        'hapax_count': len(hapax_legomena(counter)),
        'top_10_words': top_words(counter),
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
    "The quick brown fox jumps over the lazy dog. A fox is a cunning animal. "
    "Dogs are loyal companions. The dog barked at the fox. The fox ran away quickly. "
    "Both animals live in the wild. The wild is their home. Home is where the heart is. "
    "The heart of a fox is brave. Brave animals survive in the wild."
)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    else:
        text = SAMPLE_TEXT
    stats = analyze_text(text)
    print_stats(stats)
