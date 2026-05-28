import re
import sys
from collections import Counter

def tokenize_words(text):
    return re.findall("[a-zA-Z']+", text.lower())

def split_sentences(text):
    raw_sentences = re.split('(?<=[.!?])\\s+', text.strip())
    return [s for s in raw_sentences if s]

def word_counts(words):
    return Counter(words)

def top_words(counter, n=10):
    return counter.most_common(n)

def avg_word_length(words):
    if not words:
        return 0.0
    return sum((len(w) for w in words)) / len(words)

def avg_sentence_length(sentences):
    if not sentences:
        return 0.0
    lengths = [len(tokenize_words(sentence)) for sentence in sentences]
    return sum(lengths) / len(lengths)

def flesch_score(words, sentences):
    if words:
        if not sentences:
            return 0.0
    avg_sent = avg_sentence_length(sentences)
    avg_word = avg_word_length(words)
    avg_word_div3 = avg_word / 3.0
    return 206.835 - 1.015 * avg_sent - 84.6 * avg_word_div3

def hapax_legomena(word_freq):
    return [word for word, count in word_freq.items() if count == 1]

def type_token_ratio(words):
    if not words:
        return 0.0
    return len(set(words)) / len(words)

def analyze_text(text):
    words_list = tokenize_words(text)
    sentences_list = split_sentences(text)
    freq = word_counts(words_list)
    return {'total_words': len(words_list), 'unique_words': len(set(words_list)), 'total_sentences': len(sentences_list), 'avg_word_length': round(avg_word_length(words_list), 2), 'avg_sentence_length': round(avg_sentence_length(sentences_list), 2), 'flesch_score': round(flesch_score(words_list, sentences_list), 2), 'type_token_ratio': round(type_token_ratio(words_list), 4), 'hapax_count': len(hapax_legomena(freq)), 'top_10_words': top_words(freq, 10)}

def print_stats(stats):
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
SAMPLE_TEXT = 'The quick brown fox jumps over the lazy dog. A fox is a cunning animal. Dogs are loyal companions. The dog barked at the fox. The fox ran away quickly. Both animals live in the wild. The wild is their home. Home is where the heart is. The heart of a fox is brave. Brave animals survive in the wild.'
if __name__ == '__main__':
    if len(sys.argv) > 1:
        f = open(sys.argv[1])
        text = f.read()
    else:
        text = SAMPLE_TEXT
    stats = analyze_text(text)
    print_stats(stats)