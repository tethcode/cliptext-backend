from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser

import json
import os
import assemblyai as aai
import google.generativeai as genai
import yt_dlp as youtube_dl

from .models import BlogPost, Profile  # Added Profile here
from .serializers import BlogPostSerializer

# --- HELPERS ---

def yt_title(link):
    ydl_opts = {'quiet': True, 'skip_download': True}
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(link, download=False).get('title', 'Untitled')
    except: return None

def get_transcription(link):
    aai.settings.api_key = os.environ.get("AAI_API_KEY")
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(link) 
    return transcript.text

def generate_blog_from_transcription(transcription):
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(f"Write a professional blog from this transcript: {transcription}")
    return response.text.strip()

# --- AUTHENTICATION VIEWS ---

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user:
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'username': user.username
        }, status=status.HTTP_200_OK)
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

# --- USER PROFILE VIEWS ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_data(request):
    # Fetch profile (or create one if it doesn't exist)
    profile, _ = Profile.objects.get_or_create(user=request.user)
    
    # Get the absolute URL for the image so Next.js can find it
    profile_pic_url = None
    if profile.profile_pic:
        profile_pic_url = request.build_absolute_uri(profile.profile_pic.url)

    return Response({
        "username": request.user.username,
        "email": request.user.email,
        "profile_pic": profile_pic_url 
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_blog_details(request, pk):
    try:
        blog = BlogPost.objects.get(id=pk, user=request.user)
        serializer = BlogPostSerializer(blog)
        return Response(serializer.data)
    except BlogPost.DoesNotExist:
        return Response({'error': 'Blog not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])  
def update_user_profile(request):
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    
    # 1. Update text fields
    user.username = request.data.get('username', user.username)
    user.email = request.data.get('email', user.email)
    user.save()
    
    # 2. Handle Image logic
    if 'profile_pic' in request.data:
        image_data = request.data.get('profile_pic')
        
        # Case A: User sent an empty string (Remove Photo)
        if image_data == '':
            if profile.profile_pic:
                # The signal we wrote earlier handles the physical file deletion
                profile.profile_pic = None
                profile.save()
        
        # Case B: User sent a new file (Change Photo)
        elif 'profile_pic' in request.FILES:
            profile.profile_pic = request.FILES['profile_pic']
            profile.save()
    
    # 3. Build return URL
    profile_pic_url = None
    if profile.profile_pic:
        profile_pic_url = request.build_absolute_uri(profile.profile_pic.url)

    return Response({
        "username": user.username,
        "email": user.email,
        "profile_pic": profile_pic_url
    })

# --- BLOG API VIEWS ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_blog_list(request):
    blogs = BlogPost.objects.filter(user=request.user).order_by('-created_at')
    serializer = BlogPostSerializer(blogs, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_blog(request):
    yt_link = request.data.get('link')
    if not yt_link:
        return Response({'error': 'Link is required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        title = yt_title(yt_link)
        transcription = get_transcription(yt_link)
        blog_content = generate_blog_from_transcription(transcription)
        new_blog = BlogPost.objects.create(
            user=request.user,
            youtube_title=title,
            youtube_link=yt_link,
            generated_content=blog_content
        )
        return Response({'content': blog_content}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    try:
        request.user.auth_token.delete()
        return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)