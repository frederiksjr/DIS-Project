from flask import Blueprint, abort, jsonify, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .db import get_session
from .models import (
    Movie,
    RecommendationMode,
    RecommendationResult,
    RecommendationSession,
    SessionBasisMovie,
    User,
    UserMovie,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def require_json():
    if not request.is_json:
        abort(415, description="Content-Type must be application/json.")
    data = request.get_json()
    if data is None:
        abort(400, description="Invalid JSON.")
    return data


@api_bp.post("/users")
def create_user():
    data = require_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        abort(400, description="username, email, and password are required.")

    session = get_session()
    user = User(
        username=username.strip(),
        email=email.strip().lower(),
        password_hash=generate_password_hash(password),
    )
    session.add(user)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        abort(409, description="Username or email already exists.")

    return jsonify(user_id=str(user.user_id)), 201


@api_bp.post("/users/<uuid:user_id>/movies")
def log_movie(user_id):
    data = require_json()
    imdb_id = data.get("imdb_id")
    liked = data.get("liked")
    user_rating = data.get("user_rating")

    if not imdb_id or liked is None:
        abort(400, description="imdb_id and liked are required.")

    if user_rating is not None and not (1 <= float(user_rating) <= 10):
        abort(400, description="user_rating must be between 1 and 10.")

    session = get_session()
    if session.get(User, user_id) is None:
        abort(404, description="User not found.")

    if session.get(Movie, imdb_id) is None:
        abort(404, description="Movie not found.")

    entry = UserMovie(
        user_id=user_id,
        imdb_id=imdb_id,
        liked=bool(liked),
        user_rating=user_rating,
    )
    session.add(entry)
    session.commit()

    return jsonify(entry_id=str(entry.entry_id)), 201


@api_bp.post("/sessions")
def create_session():
    data = require_json()
    user_id = data.get("user_id")
    mode_value = data.get("mode")
    genre_id = data.get("genre_id")
    basis_movies = data.get("basis_movies", [])

    if not user_id or not mode_value:
        abort(400, description="user_id and mode are required.")

    try:
        mode = RecommendationMode(mode_value)
    except ValueError:
        abort(400, description="mode must be MOVIE, GENRE, PROFILE, or HYBRID.")

    if mode in {RecommendationMode.GENRE, RecommendationMode.HYBRID} and not genre_id:
        abort(400, description="genre_id is required for GENRE or HYBRID mode.")

    if mode in {RecommendationMode.MOVIE, RecommendationMode.HYBRID}:
        if not isinstance(basis_movies, list) or not basis_movies:
            abort(400, description="basis_movies must be a non-empty list for MOVIE or HYBRID mode.")

    session = get_session()
    user = session.get(User, user_id)
    if user is None:
        abort(404, description="User not found.")

    rec_session = RecommendationSession(
        user_id=user.user_id,
        genre_id=genre_id,
        mode=mode,
    )
    session.add(rec_session)
    session.flush()

    for imdb_id in basis_movies:
        if session.get(Movie, imdb_id) is None:
            abort(404, description=f"Movie not found: {imdb_id}")
        session.add(SessionBasisMovie(session_id=rec_session.session_id, imdb_id=imdb_id))

    session.commit()

    return jsonify(session_id=str(rec_session.session_id)), 201


@api_bp.post("/sessions/<uuid:session_id>/results")
def upsert_results(session_id):
    data = require_json()
    results = data.get("results")

    if not isinstance(results, list) or not results:
        abort(400, description="results must be a non-empty list.")

    session = get_session()
    if session.get(RecommendationSession, session_id) is None:
        abort(404, description="Session not found.")

    session.query(RecommendationResult).filter_by(session_id=session_id).delete()

    for item in results:
        imdb_id = item.get("imdb_id")
        rank = item.get("rank")
        supporting_user_count = item.get("supporting_user_count")
        knn_score = item.get("knn_score")

        if not imdb_id or rank is None or supporting_user_count is None or knn_score is None:
            abort(400, description="Each result needs imdb_id, rank, supporting_user_count, knn_score.")

        session.add(
            RecommendationResult(
                session_id=session_id,
                imdb_id=imdb_id,
                rank=int(rank),
                supporting_user_count=int(supporting_user_count),
                knn_score=float(knn_score),
            )
        )

    session.commit()
    return jsonify(status="ok"), 201


@api_bp.get("/sessions/<uuid:session_id>/results")
def get_results(session_id):
    session = get_session()
    results = (
        session.query(RecommendationResult)
        .filter_by(session_id=session_id)
        .order_by(RecommendationResult.rank.asc())
        .all()
    )
    return jsonify(
        results=[
            {
                "imdb_id": r.imdb_id,
                "rank": r.rank,
                "supporting_user_count": r.supporting_user_count,
                "knn_score": r.knn_score,
            }
            for r in results
        ]
    )
