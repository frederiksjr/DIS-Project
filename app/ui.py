import re
import uuid

from flask import Blueprint, render_template, request
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from .db import get_session
from .models import (
    Genre,
    Movie,
    MovieGenre,
    RecommendationMode,
    RecommendationResult,
    RecommendationSession,
    SessionBasisMovie,
    User,
)
from .recommender import run_knn

ui_bp = Blueprint(
    "ui",
    __name__,
    url_prefix="/ui",
    static_folder="static",
    template_folder="templates",
)


def _get_or_create_user(session, username):
    username = (username or "guest").strip() or "guest"
    user = session.query(User).filter_by(username=username).one_or_none()
    if user is None:
        suffix = uuid.uuid4().hex[:8]
        user = User(
            username=username,
            email=f"{username.lower().replace(' ', '_')}.{suffix}@local",
            password_hash=generate_password_hash(uuid.uuid4().hex),
        )
        session.add(user)
        session.commit()
    return user


def _resolve_basis_ids(session, basis_text):
    """
    Convert comma-separated movie title terms to a de-duplicated list of imdb_ids.

    Normalises both the search term and the DB title (strip non-alphanumeric chars,
    lowercase) so that "Spiderman" matches "Spider-Man" and "avengers endgame"
    matches "Avengers: Endgame". Each word in the term must appear in the title.
    Returns up to 3 movies per term, ordered by vote count descending.
    """
    if not basis_text or not basis_text.strip():
        return []

    # Strip everything except letters, digits, and spaces
    _norm_re = re.compile(r"[^a-z0-9 ]")

    # PostgreSQL expression that applies the same normalisation to movie titles
    norm_title = func.regexp_replace(func.lower(Movie.title), r"[^a-z0-9 ]", " ", "g")

    ids, seen = [], set()
    for term in (t.strip() for t in basis_text.split(",") if t.strip()):
        words = _norm_re.sub(" ", term.lower()).split()
        if not words:
            continue

        query = session.query(Movie.imdb_id)
        for word in words:
            query = query.filter(norm_title.ilike(f"%{word}%"))

        for r in query.order_by(Movie.imdb_vote_count.desc().nullslast()).limit(3).all():
            if r.imdb_id not in seen:
                ids.append(r.imdb_id)
                seen.add(r.imdb_id)

    return ids


def _compute_recommendations(session, user, mode, genre_id, basis_ids, top_n=10):
    """
    Create a RecommendationSession, run KNN, persist results, return result list.
    Result list items: {imdb_id, rank, supporting_user_count, knn_score}.
    """
    rec_session = RecommendationSession(
        user_id=user.user_id,
        genre_id=genre_id,
        mode=mode,
    )
    session.add(rec_session)
    session.flush()

    for imdb_id in basis_ids:
        session.add(SessionBasisMovie(session_id=rec_session.session_id, imdb_id=imdb_id))
    session.flush()

    knn_results = run_knn(session, rec_session, top_n=top_n)

    for item in knn_results:
        session.add(
            RecommendationResult(
                session_id=rec_session.session_id,
                imdb_id=item["imdb_id"],
                rank=item["rank"],
                supporting_user_count=item["supporting_user_count"],
                knn_score=item["knn_score"],
            )
        )

    session.commit()
    return knn_results


@ui_bp.route("/")
def index():
    session = get_session()
    genres = session.query(Genre).order_by(Genre.name.asc()).all()
    return render_template("index.html", genres=genres)


@ui_bp.route("/recommend", methods=["POST"])
def recommend():
    session = get_session()
    user = _get_or_create_user(session, request.form.get("username", "guest"))

    genres = session.query(Genre).order_by(Genre.name.asc()).all()
    genre_map = {g.genre_id: g.name for g in genres}

    raw_genre = request.form.get("genre_id", "").strip()
    genre_id = int(raw_genre) if raw_genre else None

    basis_ids = _resolve_basis_ids(session, request.form.get("basis_ids", ""))

    # Determine mode from what the user actually provided
    if basis_ids and genre_id:
        mode = RecommendationMode.HYBRID
    elif basis_ids:
        mode = RecommendationMode.MOVIE
    elif genre_id:
        mode = RecommendationMode.GENRE
    else:
        mode = RecommendationMode.PROFILE

    try:
        knn_results = _compute_recommendations(
            session=session,
            user=user,
            mode=mode,
            genre_id=genre_id,
            basis_ids=basis_ids,
        )
    except Exception as e:
        return f"Recommendation error: {e}", 500

    # Enrich with movie metadata for the template
    output = []
    for item in knn_results:
        movie = session.get(Movie, item["imdb_id"])
        if movie is None:
            continue
        genre_ids_for_movie = [
            r.genre_id
            for r in session.query(MovieGenre.genre_id)
            .filter(MovieGenre.imdb_id == movie.imdb_id)
            .all()
        ]
        output.append(
            {
                "title": movie.title,
                "year": movie.release_year,
                "overview": "",
                "genres": [genre_map.get(gid, "") for gid in genre_ids_for_movie],
                "imdb_id": movie.imdb_id,
                "knn_score": round(item["knn_score"], 3),
                "supporting_user_count": item["supporting_user_count"],
            }
        )

    # Normalise scores so #1 = 95%, rest are proportional.
    # Raw cosine similarity is always low on sparse vectors; relative scores are meaningful.
    if output:
        max_score = max(item["knn_score"] for item in output) or 1
        for item in output:
            item["match_pct"] = max(1, round(item["knn_score"] / max_score * 95))

    return render_template("results.html", results=output)
