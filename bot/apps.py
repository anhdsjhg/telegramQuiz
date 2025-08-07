from django.apps import AppConfig
import logging

class BotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bot'

    def ready(self):
        # Импорт делаем здесь, чтобы избежать ошибок при запуске
        from django.contrib.auth import get_user_model
        from django.db.utils import OperationalError, ProgrammingError
        User = get_user_model()

        try:
            if not User.objects.filter(username='admin').exists():
                User.objects.create_superuser(
                    username='admin',
                    email='admin@example.com',
                    password='admin123'
                )
                logging.info("✅ Superuser 'admin' created.")
        except (OperationalError, ProgrammingError) as e:
            # Базы может ещё не быть (во время миграции) — игнорируем
            logging.warning(f"⚠ Superuser not created (DB not ready yet): {e}")
        except Exception as e:
            logging.error(f"❌ Failed to create superuser: {e}")
