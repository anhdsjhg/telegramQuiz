from django.db import models
from django.db.models import F
from django.core.exceptions import ValidationError

class Quiz(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self):
        return self.title


class QuizVariant(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="variants", null=True, blank=True)
    title = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        if self.quiz:
            return f"{self.quiz.title} — {self.title}"
        return f"(Без викторины) — {self.title}"


class Question(models.Model):
    variant = models.ForeignKey(QuizVariant, on_delete=models.CASCADE, related_name="questions", null=True, blank=True)
    question = models.TextField()
    option1 = models.CharField(max_length=255, null=True, blank=True)
    option2 = models.CharField(max_length=255, null=True, blank=True)
    option3 = models.CharField(max_length=255, null=True, blank=True)
    option4 = models.CharField(max_length=255, null=True, blank=True)
    correct_answer = models.IntegerField(null=True, blank=True)

    # NEW: внешняя ссылка (URL), удобна при импорте из CSV/Google Sheets
    image_url = models.URLField(max_length=1000, null=True, blank=True, verbose_name="Изображение (URL)")

    def __str__(self):
        return self.question

    def clean(self):
        if self.correct_answer is not None and not 1 <= self.correct_answer <= 4:
            raise ValidationError("correct_answer должен быть числом от 1 до 4.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    user_id = models.BigIntegerField(unique=True)
    user_name = models.CharField(max_length=255)

    def __str__(self):
        return self.user_name


class UserResult(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    variant = models.ForeignKey(QuizVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.IntegerField()
    total = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_profile} - {self.quiz.title} ({self.score}/{self.total})"


class UserAnswer(models.Model):
    result = models.ForeignKey(UserResult, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.IntegerField()
    is_correct = models.BooleanField()

    def __str__(self):
        return f"{self.question.question[:40]}... — {'✔' if self.is_correct else '❌'}"

    def clean(self):
        if not 1 <= self.selected_option <= 4:
            raise ValidationError("selected_option должен быть от 1 до 4.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class InviteToken(models.Model):
    token = models.CharField(max_length=100, unique=True)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    usage_limit = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)

    def is_valid(self):
        return self.used_count < self.usage_limit

    def mark_used(self):
        if self.is_valid():
            self.used_count += 1
            self.save()
            return True
        return False

    def __str__(self):
        return self.token


class AllowedUser(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    invite_token = models.ForeignKey(
        'InviteToken',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    class Meta:
        unique_together = ("user_profile", "quiz")

    def __str__(self):
        return f"{self.user_profile} — {self.quiz.title}"


def clean_expired_access(user_id):
    expired_tokens = InviteToken.objects.filter(usage_limit__lte=F("used_count"))
    AllowedUser.objects.filter(user_profile__user_id=user_id, invite_token__in=expired_tokens).delete()
