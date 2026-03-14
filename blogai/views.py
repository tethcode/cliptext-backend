import os
import re
import requests
from google import genai # New library
from datetime import timedelta
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BlogPost, Profile, PasswordResetToken
from .serializers import BlogPostSerializer, ForgotPasswordSerializer, ResetPasswordSerializer

# --- AI & Transcription Config ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPADATA_API_KEY = os.environ.get("SUPADATA_API_KEY")

# Initialize the Client properly
client = genai.Client(api_key=GEMINI_API_KEY)

class ProfilePictureUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser) # Crucial for images

    def post(self, request, format=None):
        # Your upload logic here
        pass

def get_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_transcription(link):
    clean_url = link.split('?')[0]
    endpoint = "https://api.supadata.ai/v1/transcript"
    headers = {"x-api-key": SUPADATA_API_KEY}
    params = {"url": clean_url, "text": "true"}
    try:
        response = requests.get(endpoint, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            return response.json().get('content')
        elif response.status_code == 202:
            print(f"Video {clean_url} is being processed.")
            return None
        return None
    except Exception as e:
        print(f"REST API Error: {e}")
        return None

def generate_blog_from_transcription(transcription):
    try:
        # Use the new client-based syntax
        prompt = (
            "Based on the following transcript, first provide a catchy Title on the first line, "
            "then write a professional blog post.\n\nTranscript: " + transcription
        )
        
        # models.generate_content is the correct method for the new SDK
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Error: {e}")
        return None
# ----------------- AUTH VIEWS -----------------

@api_view(['POST'])
@permission_classes([AllowAny])
def api_signup(request):
    data = request.data
    password = data.get('password')
    password_confirm = data.get('confirmPassword')
    try:
        if password != password_confirm:
            return Response({'error': 'Passwords do not match'}, status=status.HTTP_400_BAD_REQUEST)
        if not data.get('username') or not data.get('email') or not data.get('password'):
            return Response({'error': 'Username, email, and password are required'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=data.get('username')).exists():
            return Response({'error': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=data.get('email')).exists():
            return Response({'error': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            username=data.get('username'),
            email=data.get('email'),
            password=data.get('password')
        )
        token, _ = Token.objects.get_or_create(user=user)

        # Send welcome email
        html_content = render_to_string("emails/signup_email.html", {"username": user.username, "frontend_url": "https://cliptext.vercel.app", "year": timezone.now().year})
        msg = EmailMultiAlternatives(
            subject="Welcome to ClipText!",
            body=f"Hello {user.username}, welcome to ClipText!",
            from_email="noreply@cliptext.com",
            to=[user.email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=True)

        return Response({'token': token.key, 'username': user.username}, status=status.HTTP_201_CREATED)
    except Exception as e:
        print(f"ERROR: {e}")


@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    if not username or not password:
        return Response({'error': 'Username and password are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    user = authenticate(username=username, password=password)
    if user:
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'username': user.username}, status=status.HTTP_200_OK)
    return Response({'error': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)


# ----------------- FORGOT & RESET PASSWORD -----------------

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data.get("user", None)

        recent_token = PasswordResetToken.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(minutes=5)
        ).exists()

        if recent_token:
            return Response(
                {"message": "If an account exists, a reset link has been sent."},
                status=status.HTTP_200_OK
    )

        # Always respond success — do NOT reveal if user exists
        if user:
            token = PasswordResetToken.objects.create(
                user=user,
                expires_at=timezone.now() + timedelta(hours=1)
            )

            reset_link = f"https://cliptext.vercel.app/reset-password/{token.token}"

            html_message = render_to_string(
                "emails/reset-password_email.html",
                {"username": user.username, "reset_link": reset_link, "year": timezone.now().year}
            )

            send_mail(
                subject="Reset your ClipText password",
                message="Use HTML email viewer",
                from_email="noreply@cliptext.com",
                recipient_list=[user.email],
                html_message=html_message,
            )

        return Response(
            {"message": "If an account exists, a reset link has been sent."},
            status=status.HTTP_200_OK
        )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.context["user"]
        token_obj = serializer.context["token"]

        user.set_password(serializer.validated_data["password"])
        user.save()

        # 🔥 delete token after use
        token_obj.delete()

        return Response(
            {"message": "Password has been reset successfully."},
            status=status.HTTP_200_OK
        )


# ----------------- USER PROFILE -----------------

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


# ----------------- BLOG GENERATION -----------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_blog(request):
    yt_link = request.data.get('link')
    if not yt_link:
        return Response({'error': 'Link is required'}, status=status.HTTP_400_BAD_REQUEST)

    transcription = get_transcription(yt_link)
    if not transcription:
        return Response({'error': 'Could not fetch transcript. The video might be new or lack captions.'}, status=status.HTTP_400_BAD_REQUEST)

    full_output = generate_blog_from_transcription(transcription)
    if not full_output:
        return Response({'error': 'AI failed to generate content'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    lines = full_output.split('\n', 1)
    title = lines[0].strip("#* ") if len(lines) > 0 else "New Blog Post"
    content = lines[1].strip() if len(lines) > 1 else full_output

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
    try:
        blog = BlogPost.objects.get(id=pk, user=request.user)
        blog.delete()
        return Response({"message": "Blog post deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
    except BlogPost.DoesNotExist:
        return Response({"error": "Blog post not found or you don't have permission to delete it."}, status=status.HTTP_404_NOT_FOUND)


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
