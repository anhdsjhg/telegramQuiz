from django.contrib import admin
from .models import Quiz, QuizVariant, Question, UserResult, UserAnswer, UserProfile
from .models import AllowedUser, InviteToken

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

    def get_user_id(self, obj):
        return obj.user_profile.user_id if obj.user_profile else None
    get_user_id.short_description = "User ID"

    def get_user_name(self, obj):
        return obj.user_profile.user_name if obj.user_profile else "-"

    def get_invite_token(self, obj):
        return obj.invite_token.token if obj.invite_token else "-"
    get_invite_token.short_description = "Invite Token"



# ------------------- Quiz and Variants -------------------
class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1


class QuizVariantInline(admin.TabularInline):
    model = QuizVariant
    extra = 1


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("id", "title")
    inlines = [QuizVariantInline]


@admin.register(QuizVariant)
class QuizVariantAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "quiz")
    list_filter = ("quiz",)
    inlines = [QuestionInline]


# ------------------- Question -------------------
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "variant", "correct_answer", "get_correct_option")
    list_filter = ("variant__quiz",)

    def get_correct_option(self, obj):
        options = [obj.option1, obj.option2, obj.option3, obj.option4]
        if 1 <= obj.correct_answer <= 4:
            return options[obj.correct_answer - 1]
        return "❌ Ошибка"
    get_correct_option.short_description = "Правильный ответ"


# ------------------- UserResult and Answers -------------------
class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    readonly_fields = ("question", "selected_option", "is_correct")


@admin.register(UserResult)
class UserResultAdmin(admin.ModelAdmin):
    list_display = ("get_user_name", "get_user_id", "variant", "quiz", "score", "total", "timestamp")
    list_filter = ("quiz", "timestamp")
    search_fields = ("user_profile__user_name", "user_profile__user_id")
    inlines = [UserAnswerInline]

    def get_user_name(self, obj):
        return obj.user_profile.user_name if obj.user_profile else "-"
    get_user_name.short_description = "User Name"

    def get_user_id(self, obj):
        return obj.user_profile.user_id if obj.user_profile else "-"
    get_user_id.short_description = "User ID"


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ["result", "question", "selected_option", "is_correct"]
    list_filter = ("is_correct", "question__variant__quiz")
    search_fields = ("result__user_id", "question__question")
