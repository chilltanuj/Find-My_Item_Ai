
import sqlite3
import re
import math
from collections import Counter


# ==========================================
# 1. CONNECT TO DATABASE
# ==========================================

conn = sqlite3.connect("findmyitem.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

query = """
SELECT
    ep.actual_match,
    l.item_name AS lost_name,
    l.category AS lost_category,
    l.description AS lost_description,
    l.location AS lost_location,
    f.item_name AS found_name,
    f.category AS found_category,
    f.description AS found_description,
    f.location AS found_location
FROM evaluation_pairs ep
JOIN reports l ON ep.lost_report_id = l.id
JOIN reports f ON ep.found_report_id = f.id
ORDER BY ep.id
"""

rows = cursor.execute(query).fetchall()
conn.close()

if not rows:
    raise ValueError("No evaluation pairs found!")

# ==========================================
# 2. PREPARE TEXT
# ==========================================

documents = []

for row in rows:
    lost = " ".join([
        row["lost_name"] or "",
        row["lost_category"] or "",
        row["lost_description"] or "",
        row["lost_location"] or ""
    ])

    found = " ".join([
        row["found_name"] or "",
        row["found_category"] or "",
        row["found_description"] or "",
        row["found_location"] or ""
    ])

    documents.extend([lost.lower(), found.lower()])


# ==========================================
# 3. TOKENIZATION + BIGRAMS
# ==========================================

stop_words = {
    "the", "is", "a", "an", "and", "or",
    "with", "in", "on", "of", "to", "for",
    "having", "has", "this", "that"
}

def tokenize(text):
    words = re.findall(r"\b[a-z0-9]+\b", text)
    words = [w for w in words if w not in stop_words]

    tokens = words[:]

    for i in range(len(words) - 1):
        tokens.append(words[i] + " " + words[i + 1])

    return tokens


tokenized_docs = [tokenize(doc) for doc in documents]

# ==========================================
# 4. TF-IDF CALCULATION
# ==========================================

N = len(tokenized_docs)

document_frequency = Counter()

for tokens in tokenized_docs:
    document_frequency.update(set(tokens))

def create_vector(tokens):
    counts = Counter(tokens)
    vector = {}

    for word, count in counts.items():
        tf = count
        idf = math.log((1 + N) /
                       (1 + document_frequency[word])) + 1

        vector[word] = tf * idf

    # L2 normalization
    magnitude = math.sqrt(sum(v * v for v in vector.values()))

    if magnitude:
        vector = {
            word: value / magnitude
            for word, value in vector.items()
        }

    return vector


vectors = [create_vector(tokens) for tokens in tokenized_docs]


# ==========================================
# 5. COSINE SIMILARITY
# ==========================================

def cosine_similarity(v1, v2):
    return sum(
        value * v2.get(word, 0)
        for word, value in v1.items()
    )


scores = []

for i in range(len(rows)):
    lost_vector = vectors[2 * i]
    found_vector = vectors[2 * i + 1]

    score = cosine_similarity(lost_vector, found_vector)
    scores.append(score)


# ==========================================
# 6. PREDICTIONS
# ==========================================

THRESHOLD = 0.20

y_true = [int(row["actual_match"]) for row in rows]

y_pred = [
    1 if score >= THRESHOLD else 0
    for score in scores
]


# ==========================================
# 7. CONFUSION MATRIX
# ==========================================

tp = sum(a == 1 and p == 1 for a, p in zip(y_true, y_pred))
tn = sum(a == 0 and p == 0 for a, p in zip(y_true, y_pred))
fp = sum(a == 0 and p == 1 for a, p in zip(y_true, y_pred))
fn = sum(a == 1 and p == 0 for a, p in zip(y_true, y_pred))
print("\nDETAILED PREDICTIONS")
print("-" * 60)

for i, row in enumerate(rows):
    print(
        f"Pair {i+1}: "
        f"Actual={y_true[i]}, "
        f"Predicted={y_pred[i]}, "
        f"Similarity={scores[i]:.4f}"
    )

print("\nSimilarity Score Range:")
print("Minimum:", min(scores))
print("Maximum:", max(scores))

print("\nConfusion Matrix:")
print("TP:", tp, "FP:", fp)
print("FN:", fn, "TN:", tn)

# ==========================================
# 8. PERFORMANCE METRICS
# ==========================================

precision = tp / (tp + fp) if tp + fp else 0
recall = tp / (tp + fn) if tp + fn else 0
sensitivity = recall

accuracy = (
    (tp + tn) / len(y_true)
    if y_true else 0
)

f1 = (
    2 * precision * recall / (precision + recall)
    if precision + recall else 0
)


# ==========================================
# 9. DISPLAY RESULTS
# ==========================================

print("\n===================================")
print("      FINDMYITEM AI EVALUATION")
print("===================================")

print("Total test pairs:", len(rows))
print("Matching threshold:", THRESHOLD)

print("\nCONFUSION MATRIX")
print("----------------------------")
print("True Positive :", tp)
print("True Negative :", tn)
print("False Positive:", fp)
print("False Negative:", fn)

print("\nPERFORMANCE METRICS")
print("----------------------------")
print(f"Precision   : {precision * 100:.2f}%")
print(f"Recall      : {recall * 100:.2f}%")
print(f"Sensitivity : {sensitivity * 100:.2f}%")
print(f"Accuracy    : {accuracy * 100:.2f}%")
print(f"F1 Score    : {f1 * 100:.2f}%")

print("\n===================================")
print("         EVALUATION COMPLETE")
print("===================================")
