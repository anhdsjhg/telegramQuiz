from django.contrib import admin
from .models import Quiz, QuizVariant, Question, UserResult, UserAnswer, UserProfile
from .models import AllowedUser, InviteToken

# ------------------- Фильтр по викторинам -------------------
class QuizFilter(admin.SimpleListFilter):
    title = 'Тема'
    parameter_name = 'quiz'

    def lookups(self, request, model_admin):
        return [(q.id, q.title) for q in Quiz.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            quiz_field = self._get_quiz_field(model_admin=queryset.model)
            return queryset.filter(**{f"{quiz_field}__id": self.value()})
        return queryset

    def _get_quiz_field(self, model_admin):
        """Определяем путь до quiz в зависимости от модели."""
        model = model_admin if not hasattr(model_admin, 'model') else model_admin.model

        if hasattr(model, "quiz"):
            return "quiz"
        elif hasattr(model, "variant"):
            return "variant__quiz"
        elif hasattr(model, "question"):
            return "question__variant__quiz"
        elif hasattr(model, "result"):
            return "result__quiz"
        return "quiz"



# ------------------- Каскадный фильтр по вариантам -------------------
class VariantFilter(admin.SimpleListFilter):
    title = "Вариант"
    parameter_name = "variant"

    def lookups(self, request, model_admin):
        quiz_id = request.GET.get("quiz")
        if quiz_id:
            return [(v.id, v.title) for v in QuizVariant.objects.filter(quiz_id=quiz_id)]
        return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                **{f"{self._get_variant_field()}__id": self.value()}
            )
        return queryset

    def _get_variant_field(self):
        """Определяем путь до variant в зависимости от модели."""
        model = self.model
        if hasattr(model, "variant"):
            return "variant"
        elif hasattr(model, "question"):
            return "question__variant"
        elif hasattr(model, "result"):
            return "result__variant"
        return "variant"

    @property
    def model(self):
        """Получаем модель, к которой применён фильтр."""
        try:
            return self.model_admin.model
        except AttributeError:
            return None

    def __init__(self, request, params, model, model_admin):
        self.model_admin = model_admin
        super().__init__(request, params, model, model_admin)


# ------------------- UserProfile -------------------
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user_id", "user_name")
    search_fields = ("user_id", "user_name")


# ------------------- InviteToken -------------------
@admin.register(InviteToken)
class InviteTokenAdmin(admin.ModelAdmin):
    list_display = ("token", "quiz", "used_count", "usage_limit", "remaining_uses")

    def remaining_uses(self, obj):
        return obj.usage_limit - obj.used_count
    remaining_uses.short_description = "Осталось попыток"


# ------------------- AllowedUser -------------------
@admin.register(AllowedUser)
class AllowedUserAdmin(admin.ModelAdmin):
    list_display = ("get_user_id", "get_user_name", "quiz", "get_invite_token")
    search_fields = ("user_profile__user_name", "user_profile__user_id")
    list_filter = (QuizFilter,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "invite_token":
            quiz_id = request.GET.get("quiz")
            if quiz_id:
                kwargs["queryset"] = InviteToken.objects.filter(quiz_id=quiz_id)
            else:
                kwargs["queryset"] = InviteToken.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_user_id(self, obj):
        return obj.user_profile.user_id if obj.user_profile else None
    get_user_id.short_description = "User ID"

    def get_user_name(self, obj):
        return obj.user_profile.user_name if obj.user_profile else "-"

    def get_invite_token(self, obj):
        return obj.invite_token.token if obj.invite_token else "-"
    get_invite_token.short_description = "Invite Token"


# ------------------- QuizVariant -------------------
class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1


@admin.register(QuizVariant)
class QuizVariantAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "quiz")
    list_filter = ("quiz",)
    inlines = [QuestionInline]


# ------------------- Question -------------------
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "variant", "correct_answer", "get_correct_option")
    list_filter = (QuizFilter, VariantFilter)

    def get_correct_option(self, obj):
        if obj.correct_answer is None:
            return "(не задано)"
        if 1 <= obj.correct_answer <= 4:
            return getattr(obj, f"option{obj.correct_answer}")
        return "(неизвестно)"


# ------------------- UserResult -------------------
class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    readonly_fields = ("question", "selected_option", "is_correct")


@admin.register(UserResult)
class UserResultAdmin(admin.ModelAdmin):
    list_display = ("get_user_name", "get_user_id", "variant", "quiz", "score", "total", "timestamp")
    list_filter = (QuizFilter, VariantFilter, "timestamp")
    search_fields = ("user_profile__user_name", "user_profile__user_id")
    inlines = [UserAnswerInline]

    def get_user_name(self, obj):
        return obj.user_profile.user_name if obj.user_profile else "-"
    get_user_name.short_description = "User Name"

    def get_user_id(self, obj):
        return obj.user_profile.user_id if obj.user_profile else "-"
    get_user_id.short_description = "User ID"


# ------------------- UserAnswer -------------------
@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ["result", "question", "selected_option", "is_correct"]
    list_filter = (QuizFilter, VariantFilter, "is_correct")
    search_fields = ("result__user_profile__user_id", "question__question")


# ------------------- Импорт CSV в Quiz -------------------
from django.http import HttpResponse
import pandas as pd
from io import TextIOWrapper
from django.shortcuts import redirect
from django.urls import path
from django.contrib import messages

class QuizAdmin(admin.ModelAdmin):
    list_display = ("id", "title")
    change_list_template = "admin/quiz_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("import-csv/", self.admin_site.admin_view(self.import_csv), name="quiz-import-csv"),
        ]
        return custom_urls + urls

    def import_csv(self, request):
        if request.method == "POST" and request.FILES.get("csv_file"):
            csv_file = TextIOWrapper(request.FILES["csv_file"].file, encoding="utf-8")
            df = pd.read_csv(csv_file)

            quiz_title = request.POST.get("quiz_title", "Импортированная тема")
            quiz, _ = Quiz.objects.get_or_create(title=quiz_title)

            for variant_title in df["variant_title"].unique():
                variant_df = df[df["variant_title"] == variant_title]
                variant, _ = QuizVariant.objects.get_or_create(title=variant_title, quiz=quiz)

                for _, row in variant_df.iterrows():
                    correct_option = None
                    for i in range(1, 5):
                        if str(row[f"is_correct_{i}"]).strip().lower() == "true":
                            correct_option = i
                            break
                    if correct_option is None:
                        continue

                    Question.objects.create(
                        variant=variant,
                        question=row["question_text"],
                        option1=row["answer_1"],
                        option2=row["answer_2"],
                        option3=row["answer_3"],
                        option4=row["answer_4"],
                        correct_answer=correct_option,
                    )

            self.message_user(request, "CSV импорт выполнен успешно ✅", messages.SUCCESS)
            return redirect("..")
        return HttpResponse("Ошибка: выберите CSV-файл", status=400)


from django.contrib.admin.sites import NotRegistered
try:
    admin.site.unregister(Quiz)
except NotRegistered:
    pass
admin.site.register(Quiz, QuizAdmin)
