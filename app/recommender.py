import math
from collections import defaultdict

import numpy as np
from sqlalchemy import func

from .models import (
    Movie,
    MovieGenre,
    MovieKeyword,
    MoviePerson,
    MoviePersonRole,
    RecommendationMode,
    SessionBasisMovie,
    UserMovie,
)

# Weights for combining content and collaborative signals
CONTENT_WEIGHT = 0.7
COLLAB_WEIGHT = 0.3

# Only top-billed actors contribute to the feature vector
MAX_BILLING_ORDER = 5

# Maximum candidate movies to score per request
CANDIDATE_LIMIT = 500


def _build_feature_matrix(db, movie_ids):
    """
    Build a feature vector for each movie in movie_ids.
    Features: genre one-hot, person weighted (1/billing_order, directors 2×),
    keyword binary, normalised avg_rating, log-normalised vote_count.
    Returns dict[imdb_id -> np.ndarray].
    """
    ids = list(movie_ids)
    if not ids:
        return {}

    genre_rows = (
        db.query(MovieGenre.imdb_id, MovieGenre.genre_id)
        .filter(MovieGenre.imdb_id.in_(ids))
        .all()
    )
    person_rows = (
        db.query(
            MoviePerson.imdb_id,
            MoviePerson.person_id,
            MoviePerson.role,
            MoviePerson.billing_order,
        )
        .filter(
            MoviePerson.imdb_id.in_(ids),
            MoviePerson.billing_order <= MAX_BILLING_ORDER,
        )
        .all()
    )
    keyword_rows = (
        db.query(MovieKeyword.imdb_id, MovieKeyword.keyword_id)
        .filter(MovieKeyword.imdb_id.in_(ids))
        .all()
    )
    movie_rows = (
        db.query(Movie.imdb_id, Movie.avg_imdb_rating, Movie.imdb_vote_count)
        .filter(Movie.imdb_id.in_(ids))
        .all()
    )

    # Build compact feature indices (only features present in this movie set)
    genre_ids = sorted({r.genre_id for r in genre_rows})
    person_ids = sorted({r.person_id for r in person_rows})
    keyword_ids = sorted({r.keyword_id for r in keyword_rows})

    p_off = len(genre_ids)
    k_off = p_off + len(person_ids)
    n_features = k_off + len(keyword_ids) + 2  # +2: normalised rating, log votes

    g_idx = {g: i for i, g in enumerate(genre_ids)}
    p_idx = {p: p_off + i for i, p in enumerate(person_ids)}
    k_idx = {k: k_off + i for i, k in enumerate(keyword_ids)}

    genres_by_movie = defaultdict(list)
    for r in genre_rows:
        genres_by_movie[r.imdb_id].append(r.genre_id)

    persons_by_movie = defaultdict(list)
    for r in person_rows:
        persons_by_movie[r.imdb_id].append((r.person_id, r.role, r.billing_order))

    keywords_by_movie = defaultdict(list)
    for r in keyword_rows:
        keywords_by_movie[r.imdb_id].append(r.keyword_id)

    movie_stats = {
        r.imdb_id: (r.avg_imdb_rating or 0.0, r.imdb_vote_count or 0)
        for r in movie_rows
    }
    max_log_votes = max((math.log1p(v) for _, v in movie_stats.values()), default=1.0) or 1.0

    vectors = {}
    for mid in ids:
        vec = np.zeros(n_features, dtype=np.float32)

        for gid in genres_by_movie.get(mid, []):
            vec[g_idx[gid]] = 1.0

        for pid, role, order in persons_by_movie.get(mid, []):
            w = 1.0 / max(1, order)
            if role == MoviePersonRole.director:
                w *= 2.0
            vec[p_idx[pid]] += w

        for kid in keywords_by_movie.get(mid, []):
            vec[k_idx[kid]] = 1.0

        # Low weight: all popular candidates have similar ratings/votes, so these
        # features would otherwise swamp the sparse genre/person signal.
        rating, votes = movie_stats.get(mid, (0.0, 0))
        vec[-2] = (rating / 10.0) * 0.3
        vec[-1] = (math.log1p(votes) / max_log_votes) * 0.3

        vectors[mid] = vec

    return vectors


def _cosine(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def run_knn(db, rec_session, top_n=10):
    """
    Run KNN recommendation for rec_session.

    Content signal: cosine similarity between each candidate and the centroid
    of the basis movie feature vectors.

    Collaborative signal: count of other users who liked at least half the
    basis movies and also liked the candidate (supporting_user_count).

    Final score: CONTENT_WEIGHT * content_sim + COLLAB_WEIGHT * normalised_collab.

    Returns list of dicts {imdb_id, rank, supporting_user_count, knn_score},
    sorted by rank ascending.
    """
    mode = rec_session.mode
    user_id = rec_session.user_id
    genre_id = rec_session.genre_id
    session_id = rec_session.session_id

    # ── 1. Basis movies ──────────────────────────────────────────────────────
    basis_ids = []
    if mode in {RecommendationMode.MOVIE, RecommendationMode.HYBRID}:
        rows = (
            db.query(SessionBasisMovie.imdb_id)
            .filter_by(session_id=session_id, excluded=False)
            .all()
        )
        basis_ids = [r.imdb_id for r in rows]

    if mode in {RecommendationMode.PROFILE, RecommendationMode.HYBRID}:
        rows = (
            db.query(UserMovie.imdb_id)
            .filter(UserMovie.user_id == user_id, UserMovie.liked.is_(True))
            .all()
        )
        seen = set(basis_ids)
        for r in rows:
            if r.imdb_id not in seen:
                basis_ids.append(r.imdb_id)
                seen.add(r.imdb_id)

    if not basis_ids:
        return []

    # ── 2. Candidate pool ────────────────────────────────────────────────────
    cq = db.query(Movie.imdb_id)
    if genre_id:
        cq = cq.join(MovieGenre, Movie.imdb_id == MovieGenre.imdb_id).filter(
            MovieGenre.genre_id == genre_id
        )
    basis_set = set(basis_ids)
    candidate_ids = [
        r.imdb_id
        for r in cq.order_by(Movie.imdb_vote_count.desc().nullslast()).limit(CANDIDATE_LIMIT).all()
        if r.imdb_id not in basis_set
    ]

    if not candidate_ids:
        return []

    # ── 3. Feature vectors ───────────────────────────────────────────────────
    all_ids = list(dict.fromkeys(basis_ids + candidate_ids))
    vectors = _build_feature_matrix(db, all_ids)

    basis_vecs = [vectors[bid] for bid in basis_ids if bid in vectors]
    if not basis_vecs:
        return []
    centroid = np.mean(basis_vecs, axis=0)

    content_scores = {
        cid: _cosine(vectors[cid], centroid)
        for cid in candidate_ids
        if cid in vectors
    }

    # ── 4. Collaborative signal ──────────────────────────────────────────────
    min_shared = max(1, len(basis_ids) // 2)
    liker_rows = (
        db.query(UserMovie.user_id)
        .filter(
            UserMovie.imdb_id.in_(basis_ids),
            UserMovie.liked.is_(True),
            UserMovie.user_id != user_id,
        )
        .group_by(UserMovie.user_id)
        .having(func.count(UserMovie.imdb_id) >= min_shared)
        .all()
    )
    liker_ids = [r.user_id for r in liker_rows]

    supporting_counts = defaultdict(int)
    if liker_ids:
        for r in (
            db.query(UserMovie.imdb_id)
            .filter(
                UserMovie.user_id.in_(liker_ids),
                UserMovie.imdb_id.in_(candidate_ids),
                UserMovie.liked.is_(True),
            )
            .all()
        ):
            supporting_counts[r.imdb_id] += 1

    max_support = max(supporting_counts.values()) if supporting_counts else 1

    # ── 5. Combine, rank, return ─────────────────────────────────────────────
    scored = []
    for cid in candidate_ids:
        support = supporting_counts.get(cid, 0)
        knn_score = (
            CONTENT_WEIGHT * content_scores.get(cid, 0.0)
            + COLLAB_WEIGHT * (support / max_support)
        )
        scored.append(
            {"imdb_id": cid, "supporting_user_count": support, "knn_score": knn_score}
        )

    scored.sort(key=lambda x: x["knn_score"], reverse=True)
    for rank, item in enumerate(scored[:top_n], start=1):
        item["rank"] = rank

    return scored[:top_n]
