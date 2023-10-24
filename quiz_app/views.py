from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, redirect, HttpResponseRedirect
from django.http import JsonResponse, Http404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import CustomUser, Message, Quiz, GroupQuiz, ScoreHolder, File
from .generator import get_question, get_q
from django.urls import reverse

import json, re
from dateutil import parser
from quiz_app.api.api_caller import OpenAi
import os
from dotenv import load_dotenv
load_dotenv()
OPEN_AI_API_KEY  = os.getenv('OPEN_AI_API_KEY')


def user_login(request):
    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')

        try: 
            user = CustomUser.objects.get(email=email)
            user = authenticate(request, email=email, password=password)
            if user:
                login(request, user)
                return redirect('home')
            else:
                return render(request, 'login.html', {'error': 'Invalid login credentials.'})
        except ObjectDoesNotExist:
            return render(request, 'login.html', {'error': "Naah, we don't know you. Signup."})
    return render(request, 'login.html')

def user_register(request):
    if request.method == "POST":
        full_name = request.POST.get("fullname")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")
        carrier = request.POST.get("profession")
        gender = request.POST.get("gender")
        
        try:
            existing_user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            existing_user = None
        
        if password1 == password2 and not existing_user:
            user = CustomUser(username=email, email=email, carrier=carrier, gender=gender, first_name=full_name)
            user.set_password(password2)
            user.save()
            login(request, user)
            return redirect('home')
        elif existing_user:
            return render(request, 'registeration.html', {'error': 'A user with this email is already registered.'})
        else:
            return render(request, 'registeration.html', {'error': 'Passwords did not match.'})
        
    return render(request, 'registeration.html')


@login_required(login_url='login')
def get_chat(request):
    user_query = request.GET.get('query')
    user = request.user
    chats = Message.objects.all().filter(user=user).order_by('-sent_date')[:4][::-1]
    response = ""
    
    opena = OpenAi(OPEN_AI_API_KEY)
    response = opena.chat(chats, user_query, user)
        
    if response:
        message1  = Message.objects.create(user=user, text=user_query, is_received = False)
        message1.save()
        message2 = Message.objects.create(user=user, text=response, is_received=True)
        message2.save()
    
    res = {}
    res['answer'] = response
    return JsonResponse(res)


@login_required(login_url='login')
def chat(request):
    query = request.GET.get("query")
    user = request.user
    chats = Message.objects.all().filter(user=user).order_by('-sent_date')[:10][::-1]
    #chats.reverse()
    response = ""
    if query:
        last_3_chats = chats  # Initialize last_3_chats to train the ai

        if len(last_3_chats) > 6:
            last_3_chats = last_3_chats[:6]
        
        if query:
            opena = OpenAi(OPEN_AI_API_KEY)
            response = opena.chat({}, query, user)
        
        if response:
            message2 = Message.objects.create(user=user, text=response, is_received=True)
            message2.save()

    return render(request, 'chat2.html', {'prev_chats': chats, 'response': response})

@login_required(login_url='login')
def user_logout(request):
    logout(request)
    return redirect('login')

def home(request):
    user = request.user
    context = {}
    if user.is_authenticated:
        context['auth'] = True
    else:
        context['auth'] = False
    return render(request, 'home2.html', context)


@login_required(login_url='login')
def handle_upload(request):
    user = request.user
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')
        num_of_questions = request.POST.get('qnumber')
        difficulty = request.POST.get('difficulty')
        spage = int(request.POST.get('spage'))
        epage = int(request.POST.get('epage'))
        comment = request.POST.get('additional_comment')
        
        if not uploaded_file or not num_of_questions or not difficulty or not spage or not epage:
            return HttpResponseRedirect(reverse('upload'))  # Redirect to upload page or appropriate URL
        
        try:
            file = File.objects.create(file=uploaded_file, subject=uploaded_file.file_name, uploaded_by=user)
            file.save()
            
            try:
                questions = get_question(uploaded_file, num_of_questions, difficulty, spage, epage, 'multiple_choice', 'chatgpt')
                if questions:
                    title = questions['questions'][0]['question']
                    quiz = Quiz.objects.create(generated_by=user, questions=str(questions), size=5, title=title)
                    quiz.save()
                    return render(request, 'quiz3.html', {'questions': questions['questions'], 'id': quiz.id})
                else:
                    # Handle case when questions are not available
                    return HttpResponseRedirect(reverse('upload')) 
            except Exception as e:
                print(f"Error generating questions: {str(e)}")
                return HttpResponseRedirect(reverse('upload')) 
        
        except Exception as e:
            print(f"Error creating File object: {str(e)}")
            return HttpResponseRedirect(reverse('upload'))  # Redirect to upload page or appropriate URL
    
    return render(request, 'upload.html')

def get_quiz(request, id):
    try:
        user = request.user
        quiz = Quiz.objects.get(pk=id)

        if quiz.generated_by.id == user.id:
            questions = quiz.questions
            questions = re.sub(r"'", '"', questions)
            print(questions)
            questions = json.loads(questions)
            return render(request, 'quiz3.html', {'questions': questions['questions'], 'id': quiz.id})

        quizs = Quiz.objects.filter(generated_by=user)
        return render(request, 'my_quizes.html', {"quizes": quizs})

    except Quiz.DoesNotExist:
        raise Http404("Quiz does not exist")
    except Exception as e:
        return redirect('error_page') 

@login_required(login_url='login')
def handle_quiz_submit(request):
    try:
        id = request.POST.get('id')
        score = request.POST.get('score')
        quiz = get_object_or_404(Quiz, pk=id)

        quiz.user_score = score
        quiz.save()
        return JsonResponse({"status": "okay"}, safe=False)

    except KeyError:
        return JsonResponse({"status": "error", "message": "Invalid request parameters"}, status=400)
    except Quiz.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Quiz does not exist"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@login_required(login_url='login')
def myquizes(request):
    try:
        user = request.user
        quizs = Quiz.objects.filter(generated_by=user)
        return render(request, 'my_quizes.html', {"quizes": quizs})

    except Exception as e:
        return render(request, 'error_page.html', {"error_message": str(e)})
@login_required(login_url='login')
def user_group_quizs(request):
    try:
        user = request.user
        group_quizzes = GroupQuiz.objects.filter(joined_members=user)
        return render(request, "joined_group_quizes.html", {"group_quizes": group_quizzes})

    except Exception as e:
        return render(request, 'error_page.html', {"error_message": str(e)})
    
@login_required(login_url='login')
def get_group_quiz_info(request, id):
    try:
        user = request.user
        data = {}
        group_quiz = get_object_or_404(GroupQuiz, pk=id)

        has_user_joined = False
        if group_quiz.joined_members.filter(id=user.id).exists():
            has_user_joined = True

        group_quiz.update_status()

        quiz = group_quiz.quiz
        questions = quiz.questions
        questions = re.sub(r"'", '"', questions)
        questions = json.loads(questions)

        if group_quiz.is_in_progress:
            data['questions'] = questions['questions']
        else:
            data['questions'] = {}

        data['has_user_joined'] = has_user_joined
        data['group_quiz'] = group_quiz

        scores = ScoreHolder.objects.filter(group_quiz=group_quiz).order_by('-score')
        data['scores'] = scores

        return render(request, 'group_quiz_comp.html', data)

    except GroupQuiz.DoesNotExist:
        raise Http404("Group quiz does not exist")
    except Exception as e:
        return render(request, 'error_page.html', {"error_message": str(e)})
    
@login_required(login_url='login')   
def handle_join_group(request, id):
    user = request.user
    group_quiz = GroupQuiz.objects.get(pk=id)
    group_quiz.update_status()
    group_quiz.joined_members.add(user)
    score = ScoreHolder(score=0,competitor=user, group_quiz=group_quiz)
    score.save()
    
    return redirect("group_quiz", id=group_quiz.id)

@login_required(login_url='login')
def create_group_quiz(request):
    user  = request.user
    if request.method == "POST":
        id = request.POST.get('id')
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time') 
            # Convert datetime strings to datetime objects
        parsed_start_date_time = parser.parse(start_time_str)
        parsed_end_date_time = parser.parse(end_time_str)
        quiz = Quiz.objects.get(pk=id)
        group_quiz = GroupQuiz(quiz=quiz, start_time=parsed_start_date_time, end_time=parsed_end_date_time, created_by=user)
        group_quiz.save()
        group_quiz.joined_members.add(user)
        group_quiz.save()
        score = ScoreHolder(score=0,competitor=user, group_quiz=group_quiz)
        score.save()
        
        return redirect('group_quizes')
    quizzes = Quiz.objects.all().filter(generated_by=user)
    return render(request, 'create_group_quiz.html', {'quizzes':quizzes})

@login_required(login_url='login')
def update_scoreboard(request):
    user = request.user
    id = request.POST.get('id')
    score = request.POST.get('score')
    score_holder = ScoreHolder.objects.get(group_quiz__quiz__id=id, competitor=user)
    score_holder.score = score
    score_holder.save()
    return JsonResponse({"status":"okay"}, safe=False)

@login_required(login_url='login')
def get_scoreboard(request):
    id = request.GET.get('id')
    data = {}
    score_holders = ScoreHolder.objects.all().filter(group_quiz__id=id)
    for score in score_holders:
        data[score.competitor.first_name] = score.score
        
    return JsonResponse(data)

@login_required(login_url='login')
def get_user_files(request):
    user = request.user
    
    
    
