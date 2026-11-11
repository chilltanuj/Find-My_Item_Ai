from pathlib import Path
from PIL import Image
import imagehash
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import math

def _text(report):
    return " ".join([
        str(report["item_name"] or ""),
        str(report["category"] or ""),
        str(report["description"] or "")
    ]).lower()

def _haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))

def _image_similarity(path_a, path_b):
    if not path_a or not path_b:
        return None
    try:
        a, b = Path(path_a), Path(path_b)
        if not a.exists() or not b.exists():
            return None
        hash_a = imagehash.phash(Image.open(a).convert("RGB"))
        hash_b = imagehash.phash(Image.open(b).convert("RGB"))
        distance = hash_a - hash_b
        return max(0.0, 1.0 - distance / len(hash_a.hash) ** 2)
    except Exception:
        return None

def rank_matches(source_report, candidates, limit=10):
    if not candidates:
        return []

    docs = [_text(source_report)] + [_text(item) for item in candidates]
    try:
        matrix = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform(docs)
        text_scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    except ValueError:
        text_scores = [0.0] * len(candidates)

    ranked = []
    for candidate, text_score in zip(candidates, text_scores):
        image_score = _image_similarity(source_report["image_path"], candidate["image_path"])
        components = [(0.70, float(text_score))]
        if image_score is not None:
            components = [(0.55, float(text_score)), (0.30, float(image_score))]
        location_km = None
        if all(source_report[k] is not None and candidate[k] is not None
               for k in ("latitude", "longitude")):
            location_km = _haversine_km(
                source_report["latitude"], source_report["longitude"],
                candidate["latitude"], candidate["longitude"]
            )
            location_score = max(0.0, 1.0 - location_km / 25.0)
            components.append((0.15, location_score))
        total_weight = sum(weight for weight, _ in components)
        score = sum(weight * value for weight, value in components) / total_weight
        ranked.append({
            "report": candidate,
            "score": round(score * 100, 1),
            "text_score": round(float(text_score) * 100, 1),
            "image_score": None if image_score is None else round(image_score * 100, 1),
            "distance_km": None if location_km is None else round(location_km, 2)
        })
    return sorted(ranked, key=lambda x: x["score"], reverse=True)[:limit]
