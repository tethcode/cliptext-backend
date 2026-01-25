import os
import re
import requests  # Replaced broken youtube_transcript_api with requests
import google.generativeai as genai

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import BlogPost, Profile
from .serializers import BlogPostSerializer

# --- CONFIGURATION ---
GEMINI_API_KEY = "AIzaSyDWzZvSQfV4O1YwLZw3U5YybCoKY66bulU"
SUPADATA_API_KEY = "sd_9d6a6e915208636fd5c55b069b13190b"  # Your working key
genai.configure(api_key=GEMINI_API_KEY)

# --- LIGHTWEIGHT HELPERS ---

def get_video_id(url):
    """Extracts the 11-character YouTube video ID."""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_transcription(link):
    """Fetches transcription via Supadata REST API (Bypassing broken local libs)."""
    # Clean tracking params from the link
    clean_url = link.split('?')[0]
    
    endpoint = "https://api.supadata.ai/v1/transcript"
    headers = {"x-api-key": SUPADATA_API_KEY}
    params = {"url": clean_url, "text": "true"}

    try:
        # We use a timeout so the Pentium doesn't hang on bad connections
        response = requests.get(endpoint, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            return response.json().get('content')
        elif response.status_code == 202:
            # If the video is being processed, you might want to tell the user to wait, 
            # but for now, we return None to trigger your existing error handling.
            print(f"Video {clean_url} is currently being transcribed by AI.")
            return None
        return None
    except Exception as e:
        print(f"REST API Error: {e}")
        return None

def generate_blog_from_transcription(transcription):
    """Uses Gemini to create a blog AND a title from the text."""
    try:
        # Changed to 1.5-flash: the most stable and fast model for this use case
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        prompt = (
            "Based on the following transcript, first provide a catchy Title on the first line, "
            "then write a professional blog post. \n\nTranscript: " + transcription
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Error: {e}")
        return None

# --- AUTH & PROFILE VIEWS (Unchanged as requested) ---

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user:
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'username': user.username}, status=status.HTTP_200_OK)
    return Response({'error': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([AllowAny])
def api_signup(request):
    data = request.data
    try:
        if User.objects.filter(username=data.get('username')).exists():
            return Response({'error': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.create_user(
            username=data.get('username'),
            email=data.get('email'),
            password=data.get('password')
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'username': user.username}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_data(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    profile_pic_url = request.build_absolute_uri(profile.profile_pic.url) if profile.profile_pic else None
    return Response({"username": request.user.username, "email": request.user.email, "profile_pic": profile_pic_url})

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])  
def update_user_profile(request):
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    user.username = request.data.get('username', user.username)
    user.email = request.data.get('email', user.email)
    user.save()
    if 'profile_pic' in request.data:
        profile.profile_pic = request.FILES.get('profile_pic')
        profile.save()
    profile_pic_url = request.build_absolute_uri(profile.profile_pic.url) if profile.profile_pic else None
    return Response({"username": user.username, "email": user.email, "profile_pic": profile_pic_url})

# --- BLOG GENERATION (Uses Title from AI) ---

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_blog(request):
    yt_link = request.data.get('link')
    if not yt_link:
        return Response({'error': 'Link is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # 1. Get transcription via Supadata REST
    transcription = get_transcription(yt_link)
    if not transcription:
        return Response({'error': 'Could not fetch transcript. The video might be new or lack captions.'}, status=status.HTTP_400_BAD_REQUEST)
            
    # 2. Let AI generate everything
    full_output = generate_blog_from_transcription(transcription)
    if not full_output:
        return Response({'error': 'AI failed to generate content'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Split title and content (AI provides Title on line 1)
    lines = full_output.split('\n', 1)
    title = lines[0].strip("#* ") if len(lines) > 0 else "New Blog Post"
    content = lines[1].strip() if len(lines) > 1 else full_output

    # 3. Save to DB
    BlogPost.objects.create(
        user=request.user,
        youtube_title=title,
        youtube_link=yt_link,
        generated_content=content
    )
    return Response({'content': content, 'title': title}, status=status.HTTP_201_CREATED)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_blog_delete(request, pk):
    """Deletes a specific blog post by ID if it belongs to the user."""
    try:
        # We filter by both ID and User for security
        blog = BlogPost.objects.get(id=pk, user=request.user)
        blog.delete()
        return Response({"message": "Blog post deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
    except BlogPost.DoesNotExist:
        return Response({"error": "Blog post not found or you don't have permission to delete it."}, status=status.HTTP_404_NOT_FOUND)

# --- LIST & DETAILS ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_blog_list(request):
    blogs = BlogPost.objects.filter(user=request.user).order_by('-created_at')
    serializer = BlogPostSerializer(blogs, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_blog_details(request, pk):
    try:
        blog = BlogPost.objects.get(id=pk, user=request.user)
        serializer = BlogPostSerializer(blog)
        return Response(serializer.data)
    except BlogPost.DoesNotExist:
        return Response({'error': 'Blog not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    request.user.auth_token.delete()
    return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)