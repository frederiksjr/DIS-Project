import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class MoviePersonRole(enum.Enum):
    actor = "actor"
    director = "director"


class RecommendationMode(enum.Enum):
    MOVIE = "MOVIE"
    GENRE = "GENRE"
    PROFILE = "PROFILE"
    HYBRID = "HYBRID"


class Movie(Base):
    __tablename__ = "movie"

    imdb_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    release_year = Column(Integer)
    avg_imdb_rating = Column(Float)
    imdb_vote_count = Column(Integer)


class Genre(Base):
    __tablename__ = "genre"

    genre_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)


class MovieGenre(Base):
    __tablename__ = "movie_genre"
    __table_args__ = (PrimaryKeyConstraint("imdb_id", "genre_id"),)

    imdb_id = Column(String, ForeignKey("movie.imdb_id", ondelete="CASCADE"), nullable=False)
    genre_id = Column(Integer, ForeignKey("genre.genre_id", ondelete="CASCADE"), nullable=False)


class Person(Base):
    __tablename__ = "person"

    person_id = Column(Integer, primary_key=True)
    imdb_person_id = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)


class MoviePerson(Base):
    __tablename__ = "movie_person"
    __table_args__ = (PrimaryKeyConstraint("imdb_id", "person_id", "role"),)

    imdb_id = Column(String, ForeignKey("movie.imdb_id", ondelete="CASCADE"), nullable=False)
    person_id = Column(Integer, ForeignKey("person.person_id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(MoviePersonRole, name="movie_person_role"), nullable=False)
    billing_order = Column(Integer, nullable=False)


class Keyword(Base):
    __tablename__ = "keyword"

    keyword_id = Column(Integer, primary_key=True)
    term = Column(String, nullable=False, unique=True)


class MovieKeyword(Base):
    __tablename__ = "movie_keyword"
    __table_args__ = (PrimaryKeyConstraint("imdb_id", "keyword_id"),)

    imdb_id = Column(String, ForeignKey("movie.imdb_id", ondelete="CASCADE"), nullable=False)
    keyword_id = Column(Integer, ForeignKey("keyword.keyword_id", ondelete="CASCADE"), nullable=False)


class User(Base):
    __tablename__ = "user"
    __table_args__ = {"quote": True}

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserMovie(Base):
    __tablename__ = "user_movie"

    entry_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.user_id", ondelete="CASCADE"), nullable=False)
    imdb_id = Column(String, ForeignKey("movie.imdb_id", ondelete="CASCADE"), nullable=False)
    liked = Column(Boolean, nullable=False)
    user_rating = Column(Float)
    logged_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ImdbRating(Base):
    __tablename__ = "imdb_rating"

    rating_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    imdb_id = Column(String, ForeignKey("movie.imdb_id", ondelete="CASCADE"), nullable=False)
    imdb_user_id = Column(String, nullable=False)
    rating = Column(Float, nullable=False)
    rated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecommendationSession(Base):
    __tablename__ = "recommendation_session"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.user_id", ondelete="CASCADE"), nullable=False)
    genre_id = Column(Integer, ForeignKey("genre.genre_id"))
    mode = Column(Enum(RecommendationMode, name="recommendation_mode"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SessionBasisMovie(Base):
    __tablename__ = "session_basis_movie"
    __table_args__ = (PrimaryKeyConstraint("session_id", "imdb_id"),)

    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    imdb_id = Column(String, ForeignKey("movie.imdb_id", ondelete="CASCADE"), nullable=False)
    excluded = Column(Boolean, nullable=False, server_default="false")


class RecommendationResult(Base):
    __tablename__ = "recommendation_result"

    result_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    imdb_id = Column(String, ForeignKey("movie.imdb_id", ondelete="CASCADE"), nullable=False)
    rank = Column(Integer, nullable=False)
    supporting_user_count = Column(Integer, nullable=False)
    knn_score = Column(Float, nullable=False)
