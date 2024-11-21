# from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django.conf import settings
from .models import Genre, Movie, Director, Actor, Review
from .serializers import *

import requests
from datetime import datetime
import random

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_API_KEY = settings.TMDB_API_KEY
TMDB_READ_ACCESS_TOKEN = settings.TMDB_READ_ACCESS_TOKEN
YOUTUBE_API_KEY = settings.YOUTUBE_API_KEY

def save_movie_from_tmdb(movie_data):
    # Step 1: 장르 데이터 처리
    genres = movie_data.pop('genres', [])
    genre_instances = []
    for genre in genres:
        genre_instance, _ = Genre.objects.get_or_create(
            genreID=genre['id'], defaults={'name': genre['name']}
        )
        genre_instances.append(genre_instance)

    # Step 2: 출연진 및 제작진 데이터 가져오기
    credits = movie_data.pop('credits', {})
    cast = credits.get('cast', [])
    crew = credits.get('crew', [])

    actor_instances = []
    director_instances = []

    for actor in cast[:10]:  # 최대 10명 저장
        actor_instance, _ = Actor.objects.get_or_create(
            actorID=actor['id'], defaults={'name': actor['name'], 'profile_path': actor.get('profile_path', '')}
        )
        actor_instances.append(actor_instance)

    for crew_member in crew:
        if crew_member['job'] == 'Director':  # 감독만 저장
            director_instance, _ = Director.objects.get_or_create(
                directorID=crew_member['id'], defaults={'name': crew_member['name'], 'profile_path': crew_member.get('profile_path', '')}
            )
            director_instances.append(director_instance)

    # Step 3: 영화 데이터 저장
    serializer_data = {
        'movieID': movie_data['id'],
        'title': movie_data['title'],
        'overview': movie_data.get('overview', ''),
        'release_date': movie_data.get('release_date', None),
        'popularity': movie_data.get('popularity', 0.0),
        'vote_average': movie_data.get('vote_average', 0.0),
        'vote_count': movie_data.get('vote_count', 0),
        'poster_path': movie_data.get('poster_path', ''),
        'backdrop_path': movie_data.get('backdrop_path', ''),
    }

    movie, created = Movie.objects.update_or_create(
        movieID=movie_data['id'], defaults=serializer_data
    )
    print('Movie saved successfully', created, movie_data['id'])

    # Step 4: Many-to-Many 관계 설정
    movie.genres.set(genre_instances)  # 장르 관계 설정
    movie.actors.set(actor_instances)  # 출연진 관계 설정
    movie.directors.set(director_instances)  # 제작진 관계 설정
    return movie


# Create your views here.
# TMDB API에서 평점 상위 10개 영화 조회 [완]
class TopRated(APIView):
    def get(self, request):
        url = f"{TMDB_BASE_URL}/movie/top_rated"
        params = {"api_key": TMDB_API_KEY, "language": "ko-KR", "page": 1}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            movies = response.json().get("results", [])[:10]
            saved_movies = [save_movie_from_tmdb(movie) for movie in movies]
            serializer = MovieSerializer(saved_movies, many=True)
            return Response({'results': serializer.data}, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch top-rated movies"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# 현재 박스오피스 상위 10개 영화 조회 [완]
class popular(APIView):
    def get(self, request):
        url = f"{TMDB_BASE_URL}/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "ko-KR",
            "page": 1,
            "region": "KR",
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            movies = response.json().get("results", [])[:10]
            return Response({ 'results': movies }, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch box-office movies"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# 최근 개봉 영화 10개 조회 [완]
class NowPlaying(APIView):
    def get(self, request):
        url = f"{TMDB_BASE_URL}/movie/now_playing"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "ko-KR",
            "region": "KR",
            "page": 1,
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            movies = response.json().get("results", [])
            today = datetime.today().date()
            # 개봉일 기준 필터링 및 정렬
            filtered_movies = [
                movie for movie in movies 
                if "release_date" in movie and datetime.strptime(movie["release_date"], "%Y-%m-%d").date() <= today
            ]
            sorted_movies = sorted(
                filtered_movies,
                key=lambda x: x.get("release_date", ""),
                reverse=True  # 내림차순 정렬
            )
            return Response({'results': sorted_movies[:10]}, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch now playing movies"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# 좋아요 하지 않은 장르 반환 [완]
class GenreMovies(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        if request.user.is_authenticated:
            return self.get_user_genre_movies(request)
        else:
            return self.get_random_genre_movies()

    def get_random_genre_movies(self):
        url = f"{TMDB_BASE_URL}/genre/movie/list"
        params = { "api_key": TMDB_API_KEY, "language": "ko-KR" }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            genres = response.json().get("genres", [])
            random_genres = random.sample(genres, 5)
            genre_movies = {}
            for genre in random_genres:
                genre_id = genre["id"]
                genre_name = genre["name"]
                movies_url = f"{TMDB_BASE_URL}/discover/movie"
                movies_params = {
                    "api_key": TMDB_API_KEY,
                    "language": "ko-KR",
                    "with_genres": genre_id,
                    "page": 1,
                }
                movies_response = requests.get(movies_url, params=movies_params)
                if movies_response.status_code == 200:
                    movies = movies_response.json().get("results", [])[:10]
                    genre_movies[genre_name] = movies
            return Response({'results': genre_movies}, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch genres"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    def get_user_genre_movies(self, request):
        # 로그인 사용자: 좋아요를 누르지 않은 장르 중 하나를 랜덤 선택해 영화 반환
        user = request.user
        liked_genres = user.liked_genres.values_list('genreID', flat=True)
        # TMDB API로 모든 장르 가져오기
        all_genres_url = f"{TMDB_BASE_URL}/genre/movie/list"
        all_genres_params = {"api_key": TMDB_API_KEY, "language": "ko-KR"}
        all_genres_response = requests.get(all_genres_url, params=all_genres_params)
        if all_genres_response.status_code == 200:
            all_genres = all_genres_response.json().get("genres", [])
            not_liked_genres = [genre for genre in all_genres if genre["id"] not in liked_genres]
            if not_liked_genres:
                random_genre = random.choice(not_liked_genres)
                genre_id = random_genre["id"]
                genre_name = random_genre["name"]
                # 해당 장르의 영화 가져오기
                movies_url = f"{TMDB_BASE_URL}/discover/movie"
                movies_params = {
                    "api_key": TMDB_API_KEY,
                    "language": "ko-KR",
                    "with_genres": genre_id,
                    "page": 1,
                }
                movies_response = requests.get(movies_url, params=movies_params)
                if movies_response.status_code == 200:
                    movies = movies_response.json().get("results", [])[:10]
                    return Response({"results": {genre_name: movies}}, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch user genre movies"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# 영화 상세 정보 조회 [수정: DB 저장 로직 추가]
class MovieDetail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, movie_id):
        try:
            movie = Movie.objects.get(movieID=movie_id)
            serializer = MovieSerializer(movie)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Movie.DoesNotExist:
            pass  # 로컬 DB에 없으면 TMDB API에서 가져옴
        movie_url = f"{TMDB_BASE_URL}/movie/{movie_id}"
        movie_params = {"api_key": TMDB_API_KEY, "language": "ko-KR"}
        movie_response = requests.get(movie_url, params=movie_params)
        if movie_response.status_code == 200:
            movie_data = movie_response.json()
            saved_movie = save_movie_from_tmdb(movie_data)
            credits_url = f"{TMDB_BASE_URL}/movie/{movie_id}/credits"
            credits_response = requests.get(credits_url, params=movie_params)
            if credits_response.status_code == 200:
                movie_data["credits"] = credits_response.json()
            serializer = MovieSerializer(saved_movie)
            movie_data.update(serializer.data)
            return Response(movie_data, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch movie details"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# 배우 상세 조회 [완]
class ActorDetail(APIView):
    def get(self, request, actor_id):
        actor_url = f"{TMDB_BASE_URL}/person/{actor_id}"
        actor_params = {"api_key": TMDB_API_KEY, "language": "ko-KR"}
        actor_response = requests.get(actor_url, params=actor_params)
        if actor_response.status_code == 200:
            actor_detail = actor_response.json()
            filmography_url = f"{TMDB_BASE_URL}/person/{actor_id}/movie_credits"
            filmography_response = requests.get(filmography_url, params=actor_params)
            if filmography_response.status_code == 200:
                actor_detail["filmography"] = filmography_response.json().get("cast", [])
            return Response(actor_detail, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch actor details"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# 감독 상세 조회 [완]
class DirectorDetail(APIView):
    def get(self, request, director_id):
        director_url = f"{TMDB_BASE_URL}/person/{director_id}"
        director_params = {"api_key": TMDB_API_KEY, "language": "ko-KR"}
        director_response = requests.get(director_url, params=director_params)
        if director_response.status_code == 200:
            director_detail = director_response.json()
            filmography_url = f"{TMDB_BASE_URL}/person/{director_id}/movie_credits"
            filmography_response = requests.get(filmography_url, params=director_params)
            if filmography_response.status_code == 200:
                director_detail["filmography"] = filmography_response.json().get("crew", [])
            return Response(director_detail, status=status.HTTP_200_OK)
        return Response(
            {"error": "Failed to fetch director details"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# 유저가 좋아요 한 영화 조회 [완]
class UserLikedMovies(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        liked_movies = user.liked_movies.all()
        serializer = UserLikedMoviesSerializer(liked_movies, many=True)
        return Response({'results': serializer.data}, status=status.HTTP_200_OK)


# 좋아요 한 배우를 기반으로 영화 5개 조회 [완]
class UserLikedActor(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        liked_actors = user.liked_actors.all()
        if liked_actors:
            random_actor = random.choice(liked_actors)
            actor_id = random_actor.actorID
            actor_name = random_actor.name
            movies_url = f"{TMDB_BASE_URL}/discover/movie"
            movies_params = {
                "api_key": TMDB_API_KEY,
                "language": "ko-KR",
                "with_cast": actor_id,
                "page": 1,
            }
            movies_response = requests.get(movies_url, params=movies_params)
            if movies_response.status_code == 200:
                movies = movies_response.json().get("results", [])[:5]
                return Response({'results': movies, 'name': actor_name}, status=status.HTTP_200_OK)
        return Response(
            {"results": {}, "error": "Failed to fetch liked actor movies"},
            status=status.HTTP_200_OK,
        )


# 유저가 좋아요 한 감독을 기반으로 영화 5개 조회 [완]
class UserLikedDirector(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        liked_directors = user.liked_directors.all()
        if liked_directors:
            random_director = random.choice(liked_directors)
            director_id = random_director.directorID
            director_name = random_director.name
            movies_url = f"{TMDB_BASE_URL}/discover/movie"
            movies_params = {
                "api_key": TMDB_API_KEY,
                "language": "ko-KR",
                "with_crew": director_id,
                "page": 1,
            }
            movies_response = requests.get(movies_url, params=movies_params)
            if movies_response.status_code == 200:
                movies = movies_response.json().get("results", [])[:5]
                return Response({'results': movies, 'name': director_name}, status=status.HTTP_200_OK)
        return Response(
            {"results": {}, "error": "Failed to fetch liked director movies"},
            status=status.HTTP_200_OK,
        )


# 유저가 좋아요 한 장르를 기반으로 영화 5개 조회 [완]
class UserLikedGenreMovies(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        liked_genres = user.liked_genres.all()
        if liked_genres:
            random_genre = random.choice(liked_genres)
            genre_id = random_genre.genreID
            genre_name = random_genre.name
            movies_url = f"{TMDB_BASE_URL}/discover/movie"
            movies_params = {
                "api_key": TMDB_API_KEY,
                "language": "ko-KR",
                "with_genres": genre_id,
                "page": 1,
            }
            movies_response = requests.get(movies_url, params=movies_params)
            if movies_response.status_code == 200:
                movies = movies_response.json().get("results", [])[:5]
                return Response({'results': {genre_name: movies}}, status=status.HTTP_200_OK)
        return Response(
            {"results": {}, "error": "Failed to fetch liked genre movies"},
            status=status.HTTP_200_OK,
        )


# 영화 리뷰 조회 및 작성 [완]
class MovieReviews(APIView):
    def get(self, request, movie_id):
        reviews = Review.objects.filter(movie_id=movie_id)
        serializer = ReviewSerializer(reviews, many=True)
        return Response({'results': serializer.data}, status=status.HTTP_200_OK)

    def post(self, request, movie_id):
        user = request.user
        data = request.data
        content = data.get("content")
        # Movie 객체 가져오기 또는 생성
        movie, created = Movie.objects.get_or_create(movieID=movie_id, defaults={
            'poster_path': data.get('poster_path', '')
        })
        # 리뷰 작성
        review = Review.objects.create(user=user, movie=movie, content=content)
        return Response(
            {
                "id": review.id,
                "content": review.content,
                "movie": {"id": movie.movieID, "poster_path": movie.poster_path},
            },
            status=status.HTTP_201_CREATED,
        )


# 영화 리뷰 수정 및 삭제 [완]
class UpdateMovieReview(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, movie_id, review_id):
        review = Review.objects.get(id=review_id, movie_id=movie_id, user=request.user)
        review.content = request.data.get("content")
        review.save()
        return Response({"message": "Review updated successfully"}, status=status.HTTP_200_OK)

    def delete(self, request, movie_id, review_id):
        review = Review.objects.get(id=review_id, movie_id=movie_id, user=request.user)
        review.delete()
        return Response({"message": "Review deleted successfully"}, status=status.HTTP_200_OK)


# 영화 좋아요 및 취소 기능 [완]
class LikeMovie(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        movie_data = request.data
        movieID = movie_data.get('movieID')
        # 1. Movie 객체 가져오기 또는 생성
        movie, created = Movie.objects.get_or_create(movieID=movieID, defaults={
            'poster_path': movie_data.get('poster_path', '')
        })
        # 3. 중복 좋아요 방지
        if user.liked_movies.filter(movieID=movieID).exists():
            return Response({"message": "You already liked this movie"}, status=status.HTTP_400_BAD_REQUEST)
        # 4. 좋아요 추가
        user.liked_movies.add(movie)
        return Response({"message": "Movie liked successfully"}, status=status.HTTP_200_OK)
    
    def delete(self, request):
        user = request.user
        movie_data = request.data
        movieID = movie_data.get('movieID')
        # 사용자가 좋아요한 영화에 있는지 확인
        movie = user.liked_movies.filter(movieID=movieID).first()
        if not movie:
            return Response({"message": "You have not liked this movie"}, status=status.HTTP_400_BAD_REQUEST)
        # 좋아요 취소
        user.liked_movies.remove(movie)
        return Response({"message": "Movie unliked successfully"}, status=status.HTTP_200_OK)


# actor 좋아요 기능 [완]
class LikeActor(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        actor_data = request.data  # 프론트에서 전송된 데이터
        actorID = actor_data.get('actorID')
        # Actor 객체 가져오기 또는 생성
        actor, created = Actor.objects.get_or_create(actorID=actorID, defaults={
            'name': actor_data.get('name', 'Unknown Actor'),
            'profile_path': actor_data.get('profile_path', '')
        })
        # 중복 좋아요 방지
        if user.liked_actors.filter(actorID=actorID).exists():
            return Response({"message": "You already liked this actor"}, status=status.HTTP_400_BAD_REQUEST)
        # 좋아요 추가
        user.liked_actors.add(actor)
        return Response({"message": "Actor liked successfully"}, status=status.HTTP_200_OK)
    
    def delete(self, request):
        user = request.user
        actorID = request.data.get('actorID')
        # 사용자가 좋아요한 배우인지 확인
        actor = user.liked_actors.filter(actorID=actorID).first()
        if not actor:
            return Response({"message": "You have not liked this actor"}, status=status.HTTP_400_BAD_REQUEST)
        # 좋아요 취소
        user.liked_actors.remove(actor)
        return Response({"message": "Actor unliked successfully"}, status=status.HTTP_200_OK)


# director 좋아요 기능
class LikeDirector(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        director_data = request.data  # 프론트에서 전송된 데이터
        directorID = director_data.get('directorID')
        # Director 객체 가져오기 또는 생성
        director, created = Director.objects.get_or_create(directorID=directorID, defaults={
            'name': director_data.get('name', 'Unknown Director'),
            'profile_path': director_data.get('profile_path', '')
        })
        # 중복 좋아요 방지
        if user.liked_directors.filter(directorID=directorID).exists():
            return Response({"message": "You already liked this director"}, status=status.HTTP_400_BAD_REQUEST)
        # 좋아요 추가
        user.liked_directors.add(director)
        return Response({"message": "Director liked successfully"}, status=status.HTTP_200_OK)
    
    def delete(self, request):
        user = request.user
        directorID = request.data.get('directorID')
        # 사용자가 좋아요한 감독인지 확인
        director = user.liked_directors.filter(directorID=directorID).first()
        if not director:
            return Response({"message": "You have not liked this director"}, status=status.HTTP_400_BAD_REQUEST)
        # 좋아요 취소
        user.liked_directors.remove(director)
        return Response({"message": "Director unliked successfully"}, status=status.HTTP_200_OK)


# 장르 좋아요 기능 [완]
class LikeGenre(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        genres_data = request.data.get("genres", [])  # 프론트에서 전송된 장르 데이터 리스트
        for genre_data in genres_data:
            genre_id = genre_data.get('genreID')
            name = genre_data.get('name')
            # Genre 객체 가져오기 또는 생성
            genre, created = Genre.objects.get_or_create(
                genreID=genre_id,
                defaults={'name': name}
            )
            # 좋아요 추가
            if not user.liked_genres.filter(genreID=genre_id).exists():
                user.liked_genres.add(genre)
        return Response({"message": "Genres liked successfully"}, status=status.HTTP_200_OK)
    
    def delete(self, request):
        user = request.user
        genre_id = request.data.get("genreID")  # 본문에서 genreID 추출
        if not genre_id:
            return Response({"message": "genreID is required"}, status=status.HTTP_400_BAD_REQUEST)
        # 사용자가 좋아요한 장르인지 확인
        genre = user.liked_genres.filter(genreID=genre_id).first()
        if not genre:
            return Response({"message": "You have not liked this genre"}, status=status.HTTP_400_BAD_REQUEST)
        # 좋아요 취소
        user.liked_genres.remove(genre)
        return Response({"message": "Genre unliked successfully"}, status=status.HTTP_200_OK)


# 리뷰 좋아요 기능 [완]
class LikeReview(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, movie_id, review_id):
        review = Review.objects.get(id=review_id, movie_id=movie_id)
        review.liked_by.add(request.user)
        return Response({"message": "Review liked successfully"}, status=status.HTTP_200_OK)


# 플레이리스트 CRUD [완]
class UserPlaylists(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        playlists = Playlist.objects.filter(user=user)
        serializer = PlaylistSerializer(playlists, many=True)
        return Response({'results': serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user  # 요청한 사용자
        data = request.data
        serializer = PlaylistSerializer(data=data)
        if serializer.is_valid(raise_exception=True):
            # Playlist 생성 및 User와 연결
            playlist = serializer.save(user=user)
            user.playlists.add(playlist)  # ManyToMany 관계에 추가
            # Many-to-Many 관계의 movies 추가
            movie_ids = data.get('movies', [])
            if movie_ids:
                movies = Movie.objects.filter(movieID__in=movie_ids)
                playlist.movies.set(movies)
            playlist.save()
            return Response({'results': PlaylistSerializer(playlist).data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UpdateDeletePlaylist(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, playlist_id):
        user = request.user
        try:
            playlist = Playlist.objects.get(id=playlist_id, user=user)
        except Playlist.DoesNotExist:
            return Response({"error": "Playlist not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = PlaylistSerializer(playlist, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'results': serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, playlist_id):
        user = request.user
        try:
            playlist = Playlist.objects.get(id=playlist_id, user=user)
        except Playlist.DoesNotExist:
            return Response({"error": "Playlist not found"}, status=status.HTTP_404_NOT_FOUND)
        
        playlist.delete()
        return Response({"message": "Playlist deleted successfully"}, status=status.HTTP_200_OK)


# 플레이리스트에 영화 추가 [완]
class PlaylistMovies(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, playlist_id):
        user = request.user
        try:
            playlist = Playlist.objects.get(id=playlist_id, user=user)
        except Playlist.DoesNotExist:
            return Response({"error": "Playlist not found"}, status=status.HTTP_404_NOT_FOUND)
        movies = playlist.movies.all()
        serializer = MovieSerializer(movies, many=True)
        return Response({'results': serializer.data}, status=status.HTTP_200_OK)
    
    def post(self, request, playlist_id):
        user = request.user
        try:
            playlist = Playlist.objects.get(id=playlist_id, user=user)
        except Playlist.DoesNotExist:
            return Response({"error": "Playlist not found"}, status=status.HTTP_404_NOT_FOUND)
        data = request.data
        movie_ids = data.get('movies', [])
        if movie_ids:
            movies = Movie.objects.filter(movieID__in=movie_ids)
            playlist.movies.add(*movies)
        return Response({"message": "Movies added to playlist successfully"}, status=status.HTTP_200_OK)
    
    def delete(self, request, playlist_id):
        user = request.user
        try:
            playlist = Playlist.objects.get(id=playlist_id, user=user)
        except Playlist.DoesNotExist:
            return Response({"error": "Playlist not found"}, status=status.HTTP_404_NOT_FOUND)
        data = request.data
        movie_ids = data.get('movies', [])
        if movie_ids:
            movies = Movie.objects.filter(movieID__in=movie_ids)
            playlist.movies.remove(*movies)
        return Response({"message": "Movies removed from playlist successfully"}, status=status.HTTP_200_OK)
