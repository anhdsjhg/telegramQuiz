from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from asgiref.sync import sync_to_async

from .models import (Quiz, QuizVariant, Question, UserResult, UserAnswer, AllowedUser, InviteToken, UserProfile)

user_states = {}

def extract_user_id(obj):
    if hasattr(obj, "effective_user") and obj.effective_user:
        return obj.effective_user.id
    elif hasattr(obj, "from_user") and obj.from_user:
        return obj.from_user.id
    return None

@sync_to_async
def get_user_profile(user_id):
    return UserProfile.objects.filter(user_id=user_id).first()

@sync_to_async
def set_user_profile_name(user_id, name):
    profile, _ = UserProfile.objects.get_or_create(user_id=user_id)
    profile.user_name = name
    profile.save()

@sync_to_async
def check_quiz_access(user_id, quiz_id):
    try:
        quiz = Quiz.objects.get(id=quiz_id)
        token = InviteToken.objects.filter(quiz=quiz).order_by('-id').first()
        if not token:
            return False, "🚫 Бұл викторинаға арналған токен жоқ."
        if token.used_count >= token.usage_limit:
            return False, "🚫 Токен қолданылып қойған. Қол жеткізу жабық."
        allowed = AllowedUser.objects.filter(user_profile__user_id=user_id, quiz=quiz).exists()
        if not allowed:
            return False, "🚫 Бұл викторинаға қол жеткізу рұқсатыңыз жоқ."
        return True, ""
    except Quiz.DoesNotExist:
        return False, "🚫 Викторина табылмады."

@sync_to_async
def check_quiz_access_by_title(user_id, quiz_title):
    try:
        quiz = Quiz.objects.get(title=quiz_title)
        token = InviteToken.objects.filter(quiz=quiz).order_by('-id').first()
        if not token:
            return None, "🚫 Бұл викторинаға арналған токен жоқ."
        if token.used_count >= token.usage_limit:
            return None, "🚫 Токен қолданылып қойған. Қол жеткізу жабық."
        return quiz, ""
    except Quiz.DoesNotExist:
        return None, "🚫 Викторина табылмады."

@sync_to_async
def get_valid_invite_token_and_quiz(code, user_id):
    try:
        token = InviteToken.objects.select_related("quiz").get(token=code)
        if token.is_valid():
            quiz = token.quiz
            already_allowed = AllowedUser.objects.filter(user_profile__user_id=user_id, quiz=quiz).exists()
            if not already_allowed:
                token.used_count += 1
                token.save()
            return quiz
    except InviteToken.DoesNotExist:
        return None
    return None

@sync_to_async
def add_allowed_user_db(user_id, quiz, user_name, invite_token=None):
    if not isinstance(quiz, Quiz):
        raise ValueError(f"Күтілген Quiz үлгісі, бірақ {type(quiz)} табылды")

    profile, _ = UserProfile.objects.get_or_create(user_id=user_id)

    if profile.user_name != user_name:
        profile.user_name = user_name
        profile.save()

    invite_token_obj = None
    if invite_token:
        try:
            invite_token_obj = InviteToken.objects.get(token=invite_token)
        except InviteToken.DoesNotExist:
            invite_token_obj = None  # если токена нет, просто None

    AllowedUser.objects.update_or_create(
        user_profile=profile,
        quiz=quiz,
        defaults={
            'invite_token': invite_token_obj
        }
    )

@sync_to_async
def clean_expired_access(user_id):
    for allowed in AllowedUser.objects.filter(user_profile__user_id=user_id):
        tokens = InviteToken.objects.filter(quiz=allowed.quiz)
        if all(not t.is_valid() for t in tokens):
            allowed.delete()

@sync_to_async
def is_user_allowed(user_id):
    return AllowedUser.objects.filter(user_profile__user_id=user_id).exists()

@sync_to_async
def get_allowed_quizzes(user_id):
    return list(Quiz.objects.filter(alloweduser__user_profile__user_id=user_id))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = extract_user_id(update)
    await clean_expired_access(user_id)

    allowed = await is_user_allowed(user_id)
    if allowed:
        user_states[user_id] = {"stage": "select_quiz"}
        await update.message.reply_text("Сәлем! Саған қолжетімді викториналар:")
        await show_quiz_options(update, context, only_allowed=True)
    else:
        keyboard = [["🔑 Менде токен бар"]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Сәлем! Қазіргі таңда сенде қол жеткізу жоқ. Егер сенде токен болса, төмендегі батырманы бас:",
            reply_markup=markup
        )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = extract_user_id(update)
    state = user_states.get(user_id, {})
    text = update.message.text.strip()

    # 🔑 Пайдаланушы "Менде токен бар" деп таңдайды
    if text == "🔑 Менде токен бар":
        user_states[user_id] = {"stage": "waiting_token"}
        await update.message.reply_text("🔐 Қол жеткізу токенін енгізіңіз:")
        return

    # 🟠 Пайдаланушы токен енгізеді
    if state.get("stage") == "waiting_token":
        quiz = await get_valid_invite_token_and_quiz(text, user_id)
        if quiz:
            user_states[user_id] = {
                "stage": "ask_name",
                "quiz_id": quiz.id,
                "quiz_obj": quiz,
                "invite_token": text
            }
            await update.message.reply_text("✅ Қол жеткізу рұқсат етілді!", reply_markup=ReplyKeyboardRemove())
            await update.message.reply_text("Енді өз атыңды жазыңыз:")
        else:
            await update.message.reply_text("❌ Токен қате. Қайтадан көріңіз.")
        return

    # ✅ Пайдаланушы аты-жөнін енгізеді
    if state.get("stage") == "ask_name":
        await handle_name(update, context)
        return

    # 🔄 Белгілі бір викторинаға арналған токен тексеру
    if state.get("stage") == "waiting_token_for_quiz":
        quiz_id = state.get("requested_quiz_id")
        try:
            token = await sync_to_async(
                InviteToken.objects.select_related("quiz").get
            )(token=text, quiz_id=quiz_id)

            if await sync_to_async(token.is_valid)():
                await sync_to_async(token.mark_used)()
                quiz = token.quiz
                profile = await get_user_profile(user_id)
                user_name = profile.user_name if profile else "Аты белгісіз"

                if not isinstance(quiz, Quiz):
                    raise ValueError("quiz Quiz үлгісінде емес")

                await add_allowed_user_db(user_id, quiz, user_name, invite_token=text)

                user_states[user_id] = {
                    "stage": "ask_name",
                    "quiz_id": quiz.id,
                    "quiz_obj": quiz
                }

                await context.bot.send_message(chat_id=user_id, text="✅ Қол жеткізу рұқсат етілді!")
                await handle_quiz_selection_with_id(user_id, quiz.id, context)
                return
            else:
                await context.bot.send_message(chat_id=user_id, text="❌ Токен жарамсыз.")
                return

        except InviteToken.DoesNotExist:
            await context.bot.send_message(chat_id=user_id, text="🚫 Токен табылмады.")
            return

    await update.message.reply_text("Бастау үшін /start командасын пайдаланыңыз.")

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = extract_user_id(update)
    state = user_states.get(user_id)
    if not state or state.get("stage") != "ask_name":
        await update.message.reply_text("Өтінемін, /start командасынан бастаңыз.")
        return

    user_name = update.message.text.strip()
    quiz_id = state.get("quiz_id")
    token_used = state.get("invite_token")  # ✅ Получаем токен

    if not quiz_id:
        user_states[user_id] = {"stage": "waiting_token"}
        await update.message.reply_text("🔑 Қол жеткізу токенін енгізіңіз:")
        return

    quiz = await sync_to_async(Quiz.objects.get)(id=quiz_id)

    await set_user_profile_name(user_id, user_name)
    await add_allowed_user_db(user_id, quiz, user_name, invite_token=token_used)  # ✅ Передаём токен

    user_states[user_id] = {
        "stage": "select_quiz",
        "name": user_name
    }

    await update.message.reply_text(f"Танысқаныма қуаныштымын, {user_name} ✨")
    await show_quiz_options(update, context, only_allowed=True)

async def show_quiz_options(update_or_query, context: ContextTypes.DEFAULT_TYPE, only_allowed=False):
    user_id = extract_user_id(update_or_query)
    quizzes = await get_allowed_quizzes(user_id) if only_allowed else await sync_to_async(list)(Quiz.objects.all())
    if not quizzes:
        await context.bot.send_message(chat_id=user_id, text="Қол жетімді викториналар жоқ.")
        return
    keyboard = [[InlineKeyboardButton(q.title, callback_data=f"quiz_{q.id}")] for q in quizzes]
    await context.bot.send_message(
        chat_id=user_id,
        text="📝 Викторинаны таңдаңыз:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_quiz_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    quiz_id = int(query.data.split("_")[1])
    user_id = extract_user_id(query)
    allowed = await sync_to_async(
        lambda: AllowedUser.objects.filter(user_profile__user_id=user_id, quiz_id=quiz_id).exists()
    )()
    if not allowed:
        user_states[user_id] = {
            "stage": "waiting_token_for_quiz",
            "requested_quiz_id": quiz_id
        }
        await query.message.reply_text("🚫 Бұл викторинаға қол жеткізу рұқсатыңыз жоқ.\nҚол жеткізу токенін енгізіңіз:")
        return
    await handle_quiz_selection_with_id(user_id, quiz_id, context)


async def handle_quiz_selection_with_id(user_id, quiz_id, context):
    access_granted, message = await check_quiz_access(user_id, quiz_id)
    if not access_granted:
        await context.bot.send_message(chat_id=user_id, text=message)
        return
    variants = await sync_to_async(list)(QuizVariant.objects.filter(quiz_id=quiz_id))
    if not variants:
        await context.bot.send_message(chat_id=user_id, text="Бұл викторина үшін нұсқалар жоқ.")
        return
    user_results = await sync_to_async(list)(
        UserResult.objects.filter(user_profile__user_id=user_id, quiz_id=quiz_id)
    )
    passed_ids = [r.variant_id for r in user_results if r.variant_id]
    keyboard = [
        [InlineKeyboardButton(f"✅ {v.title}" if v.id in passed_ids else v.title, callback_data=f"variant_{v.id}")]
        for v in variants
    ]
    await context.bot.send_message(
        chat_id=user_id,
        text="📂 Викторина нұсқасын таңдаңыз:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_variant_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        variant_id = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("❌ Қате: Вариант таңдалмады.")
        return

    user_id = extract_user_id(query)

    # Получаем вопросы по варианту
    questions = await sync_to_async(list)(
        Question.objects.filter(variant_id=variant_id)
    )

    if not questions:
        await query.message.reply_text("❌ Бұл вариантта сұрақтар табылмады.")
        return

    # Получаем сам вариант и связанную викторину
    variant = await sync_to_async(
        QuizVariant.objects.select_related("quiz").get
    )(id=variant_id)

    # Получаем имя пользователя из профиля
    user_profile = await get_user_profile(user_id)
    user_name = user_profile.user_name

    # Сохраняем состояние
    user_states[user_id] = {
        "quiz_id": variant.quiz.id,
        "variant_id": variant.id,
        "questions": questions,
        "index": 0,
        "score": 0,
        "answers": [],
        "name": user_name,
        "stage": "in_quiz",
        "answered": False,
    }

    # Отправляем сообщение о выбранной теме и варианте
    await query.message.reply_text(
        f"📘 Тақырып: *{variant.quiz.title}*\n"
        f"📑 Таңдалған вариант: *{variant.title}*",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Показываем первый вопрос
    await send_question(query, context)
async def send_question(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    user_id = extract_user_id(update_or_query)
    state = user_states.get(user_id)

    if not state:
        await context.bot.send_message(chat_id=user_id, text="⚠️ Қате орын алды. Алдымен викторинаны бастаңыз.")
        return

    index = state["index"]
    questions = state["questions"]

    # --- Если викторина завершена ---
    if index >= len(questions):
        quiz = await sync_to_async(Quiz.objects.get)(id=state["quiz_id"])
        variant = await sync_to_async(QuizVariant.objects.get)(id=state["variant_id"])
        profile = await get_user_profile(user_id)

        result = await sync_to_async(UserResult.objects.create)(
            user_profile=profile,
            quiz=quiz,
            variant=variant,
            score=state["score"],
            total=len(questions)
        )

        # Сохраняем все ответы пользователя
        for answer in state["answers"]:
            await sync_to_async(UserAnswer.objects.create)(
                result=result,
                question=answer["question"],
                selected_option=answer["selected"],
                is_correct=answer["is_correct"]
            )

        # Отправляем итоговый результат
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 Викторина аяқталды! Сіздің нәтижеңіз: {state['score']} / {len(questions)}."
        )

        # Предлагаем действия после викторины
        await context.bot.send_message(
            chat_id=user_id,
            text="Қандай әрекет жасаймыз?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Басқа викторинаны бастау", callback_data="again")],
                [InlineKeyboardButton("📊 Нәтижелерімді көру", callback_data="view_results")]
            ])
        )
        return

    # --- Получаем текущий вопрос ---
    q = questions[index]
    text = (
        f"{q.question}\n\n"
        f"1️⃣ {q.option1}\n\n"
        f"2️⃣ {q.option2}\n\n"
        f"3️⃣ {q.option3}\n\n"
        f"4️⃣ {q.option4}"
    )

    # --- Кнопки для ответов ---
    buttons = [[InlineKeyboardButton(f"{i + 1}️⃣", callback_data=str(i + 1))] for i in range(4)]
    markup = InlineKeyboardMarkup(buttons)

    # --- Отправляем вопрос с поддержкой только image_url ---
    image_url_field = getattr(q, "image_url", None)

    try:
        if image_url_field:
            # Если есть ссылка на изображение — отправляем с фото
            await context.bot.send_photo(
                chat_id=user_id,
                photo=image_url_field,
                caption=text,
                reply_markup=markup
            )
        else:
            # Если картинки нет — просто текст
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=markup
            )

    except Exception as e:
        # Если картинка не загрузилась — не прерываем викторину
        print("Ошибка при отправке фото:", e)
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=markup
        )

    state["answered"] = False

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = extract_user_id(query)
    state = user_states.get(user_id)

    if not state or "questions" not in state or "index" not in state:
        await context.bot.send_message(chat_id=user_id, text="Қате орын алды. /start командасынан қайта бастаңыз.")
        return

    if state.get("answered"):
        return

    state["answered"] = True

    # ✅ Безопасное удаление inline клавиатуры
    if query.message.reply_markup is not None:
        await query.edit_message_reply_markup(reply_markup=None)

    index = state["index"]
    questions = state["questions"]
    selected = int(query.data)
    correct = int(questions[index].correct_answer)

    feedback = (
        "✅ Дұрыс!" if selected == correct else
        f"❌ Қате. Дұрыс жауап: {[questions[index].option1, questions[index].option2, questions[index].option3, questions[index].option4][correct - 1]}"
    )

    if selected == correct:
        state["score"] += 1

    state["answers"].append({
        "question": questions[index],
        "selected": selected,
        "is_correct": selected == correct
    })

    state["index"] += 1

    await context.bot.send_message(chat_id=user_id, text=feedback)
    await send_question(query, context)

@sync_to_async
def get_results_with_variants(user_id):
    results = UserResult.objects.filter(user_profile__user_id=user_id).select_related("quiz", "variant").order_by('-id')
    output = []
    for i, r in enumerate(results, 1):
        date = r.timestamp.strftime('%d.%m.%Y %H:%M') if r.timestamp else "—"
        variant_title = r.variant.title if r.variant else "—"
        output.append(
            f"{i}) {r.quiz.title}\n"
            f"📄 {variant_title}\n"
            f"✅ Балл: {r.score}/{r.total}\n"
            f"📅 {date}\n\n"
        )
    return output

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = extract_user_id(update)
    lines = await get_results_with_variants(user_id)
    text = "📊 *Сіздің нәтижелеріңіз:*\n\n" + "".join(lines) if lines else "📭 Әзірге нәтижелер жоқ."
    parts = [text[i:i+4096] for i in range(0, len(text), 4096)]
    if update.callback_query:
        await update.callback_query.answer()  # ✅ Telegram требует ответ
        for part in parts:
            await update.callback_query.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        for part in parts:
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)

async def handle_quiz_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_quiz_options(update, context, only_allowed=False)
