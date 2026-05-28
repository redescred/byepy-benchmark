"""Text statistics analyser: word frequency, sentence stats, readability estimate."""
import re
import sys
from collections import Counter


def tokenise(text: str) -> list[str]:
    """Return lowercase words stripped of punctuation."""
    return re.findall(r"[a-zA-Z']+", text.lower())


def split_sentences(text: str) -> list[str]:
    """Split text into sentences on .!? boundaries."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in parts if s]


def word_frequencies(words: list[str]) -> Counter:
    """Return Counter of word frequencies."""
    return Counter(words)


def top_n_words(freq: Counter, n: int = 10) -> list[tuple[str, int]]:
    """Return top-n most common words."""
    return freq.most_common(n)


def mean_word_length(words: list[str]) -> float:
    """Return mean character count of all words."""
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)


def mean_sentence_length(sentences: list[str], words: list[str]) -> float:
    """Return mean word count per sentence."""
    if not sentences or not words:
        return 0.0
    word_counts = [len(tokenise(s)) for s in sentences]
    return sum(word_counts) / len(word_counts)


def flesch_score(sentences: list[str], words: list[str]) -> float:
    """Approximate Flesch Reading Ease score (no syllable counter: uses avg word length proxy)."""
    if not sentences or not words:
        return 0.0
    avg_sent_len = mean_sentence_length(sentences, words)
    avg_word_len = mean_word_length(words)
    syllable_proxy = avg_word_len / 3.0
    return 206.835 - 1.015 * avg_sent_len - 84.6 * syllable_proxy


def hapax_legomena(freq: Counter) -> list[str]:
    """Return words that appear exactly once."""
    return [word for word, count in freq.items() if count == 1]


def type_token_ratio(words: list[str]) -> float:
    """Lexical diversity: unique words / total words."""
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def analyse(text: str) -> dict:
    """Run full analysis and return results dict."""
    words = tokenise(text)
    sentences = split_sentences(text)
    freq = word_frequencies(words)
    return {
        'total_words': len(words),
        'unique_words': len(set(words)),
        'total_sentences': len(sentences),
        'avg_word_length': round(mean_word_length(words), 2),
        'avg_sentence_length': round(mean_sentence_length(sentences, words), 2),
        'flesch_score': round(flesch_score(sentences, words), 2),
        'type_token_ratio': round(type_token_ratio(words), 4),
        'hapax_count': len(hapax_legomena(freq)),
        'top_10_words': top_n_words(freq, 10),
    }


def print_report(stats: dict) -> None:
    """Print formatted stats report to stdout."""
    print(f"Total words        : {stats['total_words']}")
    print(f"Unique words       : {stats['unique_words']}")
    print(f"Total sentences    : {stats['total_sentences']}")
    print(f"Avg word length    : {stats['avg_word_length']}")
    print(f"Avg sentence length: {stats['avg_sentence_length']} words")
    print(f"Flesch score       : {stats['flesch_score']}")
    print(f"Type-token ratio   : {stats['type_token_ratio']}")
    print(f"Hapax legomena     : {stats['hapax_count']}")
    print('Top 10 words:')
    for word, count in stats['top_10_words']:
        print(f'  {word:<20} {count}')


SAMPLE_TEXT = (
    'The quick brown fox jumps over the lazy dog. '
    'A fox is a cunning animal. '
    'Dogs are loyal companions. '
    'The dog barked at the fox. '
    'The fox ran away quickly. '
    'Both animals live in the wild. '
    'The wild is their home. '
    'Home is where the heart is. '
    'The heart of a fox is brave. '
    'Brave animals survive in the wild.'
)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    else:
        text = SAMPLE_TEXT
    stats = analyse(text)
    print_report(stats)
