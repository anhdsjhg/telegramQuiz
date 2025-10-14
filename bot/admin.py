from django.contrib import admin
from django.utils.html import format_html
from django.http import HttpResponse
import pandas as pd
from io import TextIOWrapper
from django.shortcuts import redirect
from django.urls import path
from django.contrib import messages
from django.contrib.admin.sites import NotRegistered

from .models import Quiz, QuizVariant, Question, UserResult, UserAnswer, UserProfile
from .models import AllowedUser, InviteToken


# ------------------- Общий фильтр по вариантам -------------------
class VariantFilter(admin.SimpleListFilter):
    title = "Вариант"
    parameter_name = "variant"

    def lookups(self, request, model_admin):
        quiz_id = request.GET.get("variant__quiz__id__exact") or request.GET.get("quiz__id__exact")
        if quiz_id:
            return QuizVariant.objects.filter(quiz_id=quiz_id).values_list("id", "title")
        return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(variant_id=self.value())
        return queryset


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
    list_filter = ("quiz",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "invite_token":
            quiz_id = request.GET.get("quiz__id__exact")
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
    fields = ("question", "option1", "option2", "option3", "option4", "correct_answer", "image_url")


@admin.register(QuizVariant)
class QuizVariantAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "quiz")
    list_filter = ("quiz",)
    inlines = [QuestionInline]


# ------------------- Question -------------------
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "variant", "correct_answer", "get_correct_option", "image_preview")
    list_filter = ("variant__quiz", VariantFilter)
    readonly_fields = ("image_preview",)
    fields = (
        "variant", "question",
        "option1", "option2", "option3", "option4",
        "correct_answer", "image_url", "image_preview"
    )

    def get_correct_option(self, obj):
        if obj.correct_answer is None:
            return "(не задано)"
        if 1 <= obj.correct_answer <= 4:
            return getattr(obj, f"option{obj.correct_answer}")
        return "(неизвестно)"

    def image_preview(self, obj):
        if getattr(obj, "image_url", None):
            return format_html('<img src="{}" style="max-height:120px;"/>', obj.image_url)
        return "(нет изображения)"
    image_preview.short_description = "Превью"


# ------------------- UserResult -------------------
class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    readonly_fields = ("question", "selected_option", "is_correct")


@admin.register(UserResult)
class UserResultAdmin(admin.ModelAdmin):
    list_display = ("get_user_name", "get_user_id", "variant", "quiz", "score", "total", "timestamp")
    list_filter = ("quiz", VariantFilter, "timestamp")
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
    list_filter = ("question__variant__quiz", VariantFilter, "is_correct")
    search_fields = ("result__user_profile__user_id", "question__question")


# ------------------- Импорт CSV в Quiz -------------------
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
            try:
                df = pd.read_csv(csv_file)
            except Exception as e:
                self.message_user(request, f"Ошибка чтения CSV: {e}", level=messages.ERROR)
                return redirect("..")

            quiz_title = request.POST.get("quiz_title", "Импортированная тема")
            quiz, _ = Quiz.objects.get_or_create(title=quiz_title)

            required_cols = {"variant_title", "question_text", "answer_1", "answer_2", "answer_3", "answer_4"}
            if not required_cols.issubset(set(df.columns)):
                self.message_user(
                    request,
                    "CSV должен содержать колонки: variant_title, question_text, answer_1..answer_4",
                    level=messages.ERROR,
                )
                return redirect("..")

            for variant_title in df["variant_title"].unique():
                variant_df = df[df["variant_title"] == variant_title]
                variant, _ = QuizVariant.objects.get_or_create(title=variant_title, quiz=quiz)

                for _, row in variant_df.iterrows():
                    correct_option = None
                    for i in range(1, 5):
                        cell = row.get(f"is_correct_{i}", "")
                        if str(cell).strip().lower() == "true":
                            correct_option = i
                            break
                    if correct_option is None:
                        continue

                    Question.objects.create(
                        variant=variant,
                        question=str(row.get("question_text", "") or ""),
                        option1=str(row.get("answer_1", "") or ""),
                        option2=str(row.get("answer_2", "") or ""),
                        option3=str(row.get("answer_3", "") or ""),
                        option4=str(row.get("answer_4", "") or ""),
                        correct_answer=correct_option,
                        image_url=row.get("image_url", "") or None,
                    )

            self.message_user(request, "CSV импорт выполнен успешно ✅", messages.SUCCESS)
            return redirect("..")
        return HttpResponse("Ошибка: выберите CSV-файл", status=400)


# Перерегистрируем Quiz с новой админкой
try:
    admin.site.unregister(Quiz)
except NotRegistered:
    pass

admin.site.register(Quiz, QuizAdmin)
