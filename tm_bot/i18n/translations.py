"""
Internationalization module for the Telegram bot.
Provides translation layer for all user-facing messages.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class Language(Enum):
    """Supported languages."""
    EN = "en"
    ES = "es"  # TODO: Fix - was incorrectly set to "fa" (Farsi) instead of "es" (Spanish)
    FR = "fr"
    DE = "de"


@dataclass
class MessageTemplate:
    """Template for translatable messages."""
    key: str
    default_text: str
    variables: Optional[Dict[str, str]] = None


class TranslationManager:
    """Manages translations and message formatting."""

    def __init__(self, default_language: Language = Language.EN):
        self.default_language = default_language
        self.translations = self._load_translations()

    def _load_translations(self) -> Dict[Language, Dict[str, str]]:
        """Load all translations."""
        return {
            Language.EN: self._get_english_translations(),
            Language.ES: self._get_spanish_translations(),
            Language.FR: self._get_french_translations(),
            Language.DE: self._get_german_translations(),
        }

    def _get_english_translations(self) -> Dict[str, str]:
        """English translations."""
        return {
            # Welcome messages
            "welcome_new": "Hi! Welcome to plan keeper. Your user directory has been created.",
            "welcome_return": "Hi! Welcome back.",

            # Commands
            "no_promises": "You have no promises. You want to add one? For example, you could promise to 'deep work 6 hours a day, 5 days a week', 'spend 2 hours a week on playing guitar.'",
            "promises_list_header": "Your promises:",
            "promise_item": "* {id}: {text}",

            # Nightly reminders
            "nightly_header": "🌙 *Nightly reminders*",
            "nightly_header_with_more": "🌙 *Nightly reminders*\nHere are today's top 3. Tap \"Show more\" for additional suggestions.",
            "nightly_question": "How much time did you spend today on *{promise_text}*?",
            "show_more_button": "Show more ({count})",
            "thats_all": "✅ That's all for today.",

            # Morning reminders
            "morning_header": "☀️ *Morning Focus*\nHere are the top 3 to prioritize today. Pick a quick time or adjust, then get rolling.",
            "morning_question": "🌸 What about *{promise_text}* today? Ready to start?",

            # Weekly reports
            "weekly_header": "Weekly: {date_range}",
            "weekly_no_data": "No data available for this week.",

            # Timezone
            "timezone_invalid": "Invalid timezone. Example: /settimezone Europe/Paris",
            "timezone_set": "Timezone set to {timezone}",
            "timezone_location_request": "Please share your location once so I can set your timezone.",
            "timezone_location_failed": "Sorry, I couldn't detect your timezone. You can set it manually, e.g. /settimezone Europe/Paris",
            "timezone_location_success": "Timezone set to {timezone}. I'll schedule reminders in your local time.",

            # Pomodoro
            "pomodoro_start": "Pomodoro Timer: 25:00",
            "pomodoro_paused": "Pomodoro Timer Paused.",
            "pomodoro_stopped": "Pomodoro Timer Stopped.",
            "pomodoro_finished": "Pomodoro Timer (25min) Finished! 🎉",
            "pomodoro_break": "Time's up! Take a break or start another session.",

            # Session management
            "session_started": "Timer started",
            "session_paused": "Session paused",
            "session_resumed": "Session resumed",
            "session_finished": "Session finished",
            "session_logged": "Logged {time} for *{promise_id}*. ✅",
            "session_skipped": "Noted. We'll skip this one today. ✅",
            "session_snoozed": "#{promise_id} snoozed for {minutes}m. ⏰",
            "session_ready": "*{promise_text}* — ready to start?",

            # Time tracking
            "time_selected": "{time} selected",
            "time_spent": "Spent {time} on #{promise_id}.",
            "time_added": "Added {time}",
            "time_snoozed": "Snoozed {minutes}m",

            # Promise management
            "promise_remind_next_week": "#{promise_id} will be silent until monday.",
            "promise_deleted": "Promise deleted",
            "promise_report": "Promise report generated",

            # Zana insights
            "zana_insights": "Insights from Zana:\n{insights}",
            "zana_no_promises": "You have no promises to report on.",

            # Error messages
            "error_invalid_input": "⚠️ Invalid input: {error}",
            "error_general": "❌ Sorry, I couldn't complete this action. Please try again.\nError: {error}",
            "error_unexpected": "🔧 Something went wrong. Please try again later. Error: {error}",
            "error_llm_trouble": "I'm having trouble understanding that. Could you rephrase?",
            "error_llm_parsing": "Error parsing response",
            "error_llm_unexpected": "Something went wrong. Error: {error}",

            # Keyboard buttons
            "btn_start": "Start",
            "btn_pause": "Pause",
            "btn_stop": "Stop",
            "btn_resume": "Resume",
            "btn_finish": "Finish",
            "btn_refresh": "🔄 Refresh",
            "btn_show_more": "Show more promises",
            "btn_log_time": "Log time for #{promise_id}",
            "btn_none": "🙅 None",
            "btn_skip_week": "⏭️ Skip (wk)",
            "btn_not_today": "Not today 🙅",
            "btn_more": "More…",
            "btn_yes_delete": "Yes (delete)",
            "btn_no_cancel": "No (cancel)",
            "btn_looks_right": "Looks right ✅ ({time})",
            "btn_adjust": "Adjust…",
            "btn_share_location": "Share location",

            # Time formatting
            "time_none": "None",
            "time_minutes": "{minutes}m",
            "time_hours": "{hours}h",
            "time_hours_minutes": "{hours}h {minutes}m",
        }

    def _get_spanish_translations(self) -> Dict[str, str]:
        """Spanish translations."""
        return {
            # Welcome messages
            "welcome_new": "¡Hola! Bienvenido al plan keeper. Se ha creado tu directorio de usuario.",
            "welcome_return": "¡Hola! Bienvenido de nuevo.",

            # Commands
            "no_promises": "No tienes promesas. ¿Quieres agregar una? Por ejemplo, podrías prometer 'trabajo profundo 6 horas al día, 5 días a la semana', 'dedicar 2 horas a la semana a tocar guitarra.'",
            "promises_list_header": "Tus promesas:",
            "promise_item": "* {id}: {text}",

            # Nightly reminders
            "nightly_header": "🌙 *Recordatorios nocturnos*",
            "nightly_header_with_more": "🌙 *Recordatorios nocturnos*\nAquí están los 3 principales de hoy. Toca \"Mostrar más\" para sugerencias adicionales.",
            "nightly_question": "¿Cuánto tiempo dedicaste hoy a *{promise_text}*?",
            "show_more_button": "Mostrar más ({count})",
            "thats_all": "✅ Eso es todo por hoy.",

            # Morning reminders
            "morning_header": "☀️ *Enfoque matutino*\nAquí están los 3 principales para priorizar hoy. Elige un tiempo rápido o ajusta, luego ponte en marcha.",
            "morning_question": "🌸 ¿Qué tal *{promise_text}* hoy? ¿Listo para empezar?",

            # Weekly reports
            "weekly_header": "Semanal: {date_range}",
            "weekly_no_data": "No hay datos disponibles para esta semana.",

            # Timezone
            "timezone_invalid": "Zona horaria inválida. Ejemplo: /settimezone Europe/Madrid",
            "timezone_set": "Zona horaria establecida en {timezone}",
            "timezone_location_request": "Por favor comparte tu ubicación una vez para que pueda establecer tu zona horaria.",
            "timezone_location_failed": "Lo siento, no pude detectar tu zona horaria. Puedes establecerla manualmente, ej. /settimezone Europe/Madrid",
            "timezone_location_success": "Zona horaria establecida en {timezone}. Programaré recordatorios en tu hora local.",

            # Pomodoro
            "pomodoro_start": "Temporizador Pomodoro: 25:00",
            "pomodoro_paused": "Temporizador Pomodoro Pausado.",
            "pomodoro_stopped": "Temporizador Pomodoro Detenido.",
            "pomodoro_finished": "¡Temporizador Pomodoro (25min) Terminado! 🎉",
            "pomodoro_break": "¡Se acabó el tiempo! Toma un descanso o inicia otra sesión.",

            # Session management
            "session_started": "Temporizador iniciado",
            "session_paused": "Sesión pausada",
            "session_resumed": "Sesión reanudada",
            "session_finished": "Sesión terminada",
            "session_logged": "Registrado {time} para *{promise_id}*. ✅",
            "session_skipped": "Anotado. Omitiremos este hoy. ✅",
            "session_snoozed": "#{promise_id} pospuesto por {minutes}m. ⏰",
            "session_ready": "*{promise_text}* — ¿listo para empezar?",

            # Time tracking
            "time_selected": "{time} seleccionado",
            "time_spent": "Dedicado {time} a #{promise_id}.",
            "time_added": "Agregado {time}",
            "time_snoozed": "Pospuesto {minutes}m",

            # Promise management
            "promise_remind_next_week": "#{promise_id} estará silencioso hasta el lunes.",
            "promise_deleted": "Promesa eliminada",
            "promise_report": "Reporte de promesa generado",

            # Zana insights
            "zana_insights": "Perspectivas de Zana:\n{insights}",
            "zana_no_promises": "No tienes promesas para reportar.",

            # Error messages
            "error_invalid_input": "⚠️ Entrada inválida: {error}",
            "error_general": "❌ Lo siento, no pude completar esta acción. Por favor intenta de nuevo.\nError: {error}",
            "error_unexpected": "🔧 Algo salió mal. Por favor intenta más tarde. Error: {error}",
            "error_llm_trouble": "Tengo problemas para entender eso. ¿Podrías reformularlo?",
            "error_llm_parsing": "Error al analizar respuesta",
            "error_llm_unexpected": "Algo salió mal. Error: {error}",

            # Keyboard buttons
            "btn_start": "Iniciar",
            "btn_pause": "Pausar",
            "btn_stop": "Detener",
            "btn_resume": "Reanudar",
            "btn_finish": "Terminar",
            "btn_refresh": "🔄 Actualizar",
            "btn_show_more": "Mostrar más promesas",
            "btn_log_time": "Registrar tiempo para #{promise_id}",
            "btn_none": "🙅 Ninguno",
            "btn_skip_week": "⏭️ Omitir (sem)",
            "btn_not_today": "No hoy 🙅",
            "btn_more": "Más…",
            "btn_yes_delete": "Sí (eliminar)",
            "btn_no_cancel": "No (cancelar)",
            "btn_looks_right": "Se ve bien ✅ ({time})",
            "btn_adjust": "Ajustar…",
            "btn_share_location": "Compartir ubicación",

            # Time formatting
            "time_none": "Ninguno",
            "time_minutes": "{minutes}m",
            "time_hours": "{hours}h",
            "time_hours_minutes": "{hours}h {minutes}m",
        }

    def _get_french_translations(self) -> Dict[str, str]:
        """French translations."""
        return {
            # Welcome messages
            "welcome_new": "Salut ! Bienvenue dans plan keeper. Votre répertoire utilisateur a été créé.",
            "welcome_return": "Salut ! Bon retour.",

            # Commands
            "no_promises": "Vous n'avez pas de promesses. Vous voulez en ajouter une ? Par exemple, vous pourriez promettre 'travail approfondi 6 heures par jour, 5 jours par semaine', 'passer 2 heures par semaine à jouer de la guitare.'",
            "promises_list_header": "Vos promesses :",
            "promise_item": "* {id} : {text}",

            # Nightly reminders
            "nightly_header": "🌙 *Rappels nocturnes*",
            "nightly_header_with_more": "🌙 *Rappels nocturnes*\nVoici les 3 principaux d'aujourd'hui. Appuyez sur \"Afficher plus\" pour des suggestions supplémentaires.",
            "nightly_question": "Combien de temps avez-vous passé aujourd'hui sur *{promise_text}* ?",
            "show_more_button": "Afficher plus ({count})",
            "thats_all": "✅ C'est tout pour aujourd'hui.",

            # Morning reminders
            "morning_header": "☀️ *Focus matinal*\nVoici les 3 principaux à prioriser aujourd'hui. Choisissez un temps rapide ou ajustez, puis commencez.",
            "morning_question": "🌸 Qu'en est-il de *{promise_text}* aujourd'hui ? Prêt à commencer ?",

            # Weekly reports
            "weekly_header": "Hebdomadaire : {date_range}",
            "weekly_no_data": "Aucune donnée disponible pour cette semaine.",

            # Timezone
            "timezone_invalid": "Fuseau horaire invalide. Exemple : /settimezone Europe/Paris",
            "timezone_set": "Fuseau horaire défini sur {timezone}",
            "timezone_location_request": "Veuillez partager votre localisation une fois pour que je puisse définir votre fuseau horaire.",
            "timezone_location_failed": "Désolé, je n'ai pas pu détecter votre fuseau horaire. Vous pouvez le définir manuellement, ex. /settimezone Europe/Paris",
            "timezone_location_success": "Fuseau horaire défini sur {timezone}. Je programmerai les rappels dans votre heure locale.",

            # Pomodoro
            "pomodoro_start": "Minuteur Pomodoro : 25:00",
            "pomodoro_paused": "Minuteur Pomodoro en pause.",
            "pomodoro_stopped": "Minuteur Pomodoro arrêté.",
            "pomodoro_finished": "Minuteur Pomodoro (25min) terminé ! 🎉",
            "pomodoro_break": "C'est l'heure ! Prenez une pause ou commencez une autre session.",

            # Session management
            "session_started": "Minuteur démarré",
            "session_paused": "Session en pause",
            "session_resumed": "Session reprise",
            "session_finished": "Session terminée",
            "session_logged": "Enregistré {time} pour *{promise_id}*. ✅",
            "session_skipped": "Noté. Nous ignorerons celui-ci aujourd'hui. ✅",
            "session_snoozed": "#{promise_id} reporté de {minutes}m. ⏰",
            "session_ready": "*{promise_text}* — prêt à commencer ?",

            # Time tracking
            "time_selected": "{time} sélectionné",
            "time_spent": "Passé {time} sur #{promise_id}.",
            "time_added": "Ajouté {time}",
            "time_snoozed": "Reporté {minutes}m",

            # Promise management
            "promise_remind_next_week": "#{promise_id} sera silencieux jusqu'à lundi.",
            "promise_deleted": "Promesse supprimée",
            "promise_report": "Rapport de promesse généré",

            # Zana insights
            "zana_insights": "Perspectives de Zana :\n{insights}",
            "zana_no_promises": "Vous n'avez pas de promesses à rapporter.",

            # Error messages
            "error_invalid_input": "⚠️ Entrée invalide : {error}",
            "error_general": "❌ Désolé, je n'ai pas pu terminer cette action. Veuillez réessayer.\nErreur : {error}",
            "error_unexpected": "🔧 Quelque chose s'est mal passé. Veuillez réessayer plus tard. Erreur : {error}",
            "error_llm_trouble": "J'ai du mal à comprendre cela. Pourriez-vous reformuler ?",
            "error_llm_parsing": "Erreur d'analyse de la réponse",
            "error_llm_unexpected": "Quelque chose s'est mal passé. Erreur : {error}",

            # Keyboard buttons
            "btn_start": "Démarrer",
            "btn_pause": "Pause",
            "btn_stop": "Arrêter",
            "btn_resume": "Reprendre",
            "btn_finish": "Terminer",
            "btn_refresh": "🔄 Actualiser",
            "btn_show_more": "Afficher plus de promesses",
            "btn_log_time": "Enregistrer le temps pour #{promise_id}",
            "btn_none": "🙅 Aucun",
            "btn_skip_week": "⏭️ Ignorer (sem)",
            "btn_not_today": "Pas aujourd'hui 🙅",
            "btn_more": "Plus…",
            "btn_yes_delete": "Oui (supprimer)",
            "btn_no_cancel": "Non (annuler)",
            "btn_looks_right": "Ça a l'air bien ✅ ({time})",
            "btn_adjust": "Ajuster…",
            "btn_share_location": "Partager la localisation",

            # Time formatting
            "time_none": "Aucun",
            "time_minutes": "{minutes}m",
            "time_hours": "{hours}h",
            "time_hours_minutes": "{hours}h {minutes}m",
        }

    def _get_german_translations(self) -> Dict[str, str]:
        """German translations."""
        return {
            # Welcome messages
            "welcome_new": "Hallo! Willkommen beim Plan Keeper. Ihr Benutzerverzeichnis wurde erstellt.",
            "welcome_return": "Hallo! Willkommen zurück.",

            # Commands
            "no_promises": "Sie haben keine Versprechen. Möchten Sie eines hinzufügen? Zum Beispiel könnten Sie versprechen 'tiefe Arbeit 6 Stunden am Tag, 5 Tage die Woche', '2 Stunden pro Woche Gitarre spielen.'",
            "promises_list_header": "Ihre Versprechen:",
            "promise_item": "* {id}: {text}",

            # Nightly reminders
            "nightly_header": "🌙 *Abendliche Erinnerungen*",
            "nightly_header_with_more": "🌙 *Abendliche Erinnerungen*\nHier sind die Top 3 von heute. Tippen Sie auf \"Mehr anzeigen\" für zusätzliche Vorschläge.",
            "nightly_question": "Wie viel Zeit haben Sie heute mit *{promise_text}* verbracht?",
            "show_more_button": "Mehr anzeigen ({count})",
            "thats_all": "✅ Das ist alles für heute.",

            # Morning reminders
            "morning_header": "☀️ *Morgendlicher Fokus*\nHier sind die Top 3, die Sie heute priorisieren sollten. Wählen Sie eine schnelle Zeit oder passen Sie an, dann legen Sie los.",
            "morning_question": "🌸 Wie wäre es mit *{promise_text}* heute? Bereit zu starten?",

            # Weekly reports
            "weekly_header": "Wöchentlich: {date_range}",
            "weekly_no_data": "Keine Daten für diese Woche verfügbar.",

            # Timezone
            "timezone_invalid": "Ungültige Zeitzone. Beispiel: /settimezone Europe/Berlin",
            "timezone_set": "Zeitzone auf {timezone} gesetzt",
            "timezone_location_request": "Bitte teilen Sie einmal Ihren Standort, damit ich Ihre Zeitzone einstellen kann.",
            "timezone_location_failed": "Entschuldigung, ich konnte Ihre Zeitzone nicht erkennen. Sie können sie manuell einstellen, z.B. /settimezone Europe/Berlin",
            "timezone_location_success": "Zeitzone auf {timezone} gesetzt. Ich werde Erinnerungen in Ihrer Ortszeit planen.",

            # Pomodoro
            "pomodoro_start": "Pomodoro-Timer: 25:00",
            "pomodoro_paused": "Pomodoro-Timer pausiert.",
            "pomodoro_stopped": "Pomodoro-Timer gestoppt.",
            "pomodoro_finished": "Pomodoro-Timer (25min) beendet! 🎉",
            "pomodoro_break": "Zeit ist um! Machen Sie eine Pause oder starten Sie eine weitere Session.",

            # Session management
            "session_started": "Timer gestartet",
            "session_paused": "Session pausiert",
            "session_resumed": "Session fortgesetzt",
            "session_finished": "Session beendet",
            "session_logged": "{time} für *{promise_id}* protokolliert. ✅",
            "session_skipped": "Vermerkt. Wir überspringen dieses heute. ✅",
            "session_snoozed": "#{promise_id} um {minutes}m verschoben. ⏰",
            "session_ready": "*{promise_text}* — bereit zu starten?",

            # Time tracking
            "time_selected": "{time} ausgewählt",
            "time_spent": "{time} für #{promise_id} verbracht.",
            "time_added": "{time} hinzugefügt",
            "time_snoozed": "{minutes}m verschoben",

            # Promise management
            "promise_remind_next_week": "#{promise_id} wird bis Montag stumm sein.",
            "promise_deleted": "Versprechen gelöscht",
            "promise_report": "Versprechen-Bericht generiert",

            # Zana insights
            "zana_insights": "Einblicke von Zana:\n{insights}",
            "zana_no_promises": "Sie haben keine Versprechen zu berichten.",

            # Error messages
            "error_invalid_input": "⚠️ Ungültige Eingabe: {error}",
            "error_general": "❌ Entschuldigung, ich konnte diese Aktion nicht abschließen. Bitte versuchen Sie es erneut.\nFehler: {error}",
            "error_unexpected": "🔧 Etwas ist schief gelaufen. Bitte versuchen Sie es später erneut. Fehler: {error}",
            "error_llm_trouble": "Ich habe Schwierigkeiten, das zu verstehen. Könnten Sie es umformulieren?",
            "error_llm_parsing": "Fehler beim Parsen der Antwort",
            "error_llm_unexpected": "Etwas ist schief gelaufen. Fehler: {error}",

            # Keyboard buttons
            "btn_start": "Start",
            "btn_pause": "Pause",
            "btn_stop": "Stopp",
            "btn_resume": "Fortsetzen",
            "btn_finish": "Beenden",
            "btn_refresh": "🔄 Aktualisieren",
            "btn_show_more": "Mehr Versprechen anzeigen",
            "btn_log_time": "Zeit für #{promise_id} protokollieren",
            "btn_none": "🙅 Keine",
            "btn_skip_week": "⏭️ Überspringen (Woche)",
            "btn_not_today": "Nicht heute 🙅",
            "btn_more": "Mehr…",
            "btn_yes_delete": "Ja (löschen)",
            "btn_no_cancel": "Nein (abbrechen)",
            "btn_looks_right": "Sieht richtig aus ✅ ({time})",
            "btn_adjust": "Anpassen…",
            "btn_share_location": "Standort teilen",

            # Time formatting
            "time_none": "Keine",
            "time_minutes": "{minutes}m",
            "time_hours": "{hours}h",
            "time_hours_minutes": "{hours}h {minutes}m",
        }

    def get_message(self, key: str, language: Optional[Language] = None, **kwargs) -> str:
        """Get translated message with variable substitution."""
        lang = language or self.default_language
        translations = self.translations.get(lang, self.translations[self.default_language])

        message = translations.get(key, key)

        # Substitute variables
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError as e:
                # If a variable is missing, log and return the message as-is
                import logging
                logging.warning(f"Missing variable {e} for message key '{key}' in language {lang.value}")

        return message

    def get_user_language(self, user_id: int) -> Language:
        """Get user's preferred language. For now, returns default language."""
        # TODO: Implement user language preference storage in settings repository
        return self.default_language


# Global instance
_translation_manager = TranslationManager()


def get_message(key: str, language: Optional[Language] = None, **kwargs) -> str:
    """Convenience function to get translated message."""
    return _translation_manager.get_message(key, language, **kwargs)


def get_user_language(user_id: int) -> Language:
    """Convenience function to get user's language."""
    return _translation_manager.get_user_language(user_id)
