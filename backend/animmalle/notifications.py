"""Notification facultative des éditions de pages ; aucun secret dans les erreurs."""
from email.message import EmailMessage
import smtplib
import ssl

from flask import current_app


def page_changed(name):
    settings = current_app.extensions['settings'].get('mail', {})
    if not settings.get('enabled', False):
        return 'disabled'
    message = EmailMessage()
    message['Subject'] = f'[Animmalle] Page modifiée : {name}'
    message['From'] = settings['sender']
    message['To'] = ', '.join(settings['recipients'])
    message.set_content(f'La page {name} a été modifiée dans Animmalle.')
    try:
        with smtplib.SMTP(settings['host'], settings['port'], timeout=5) as client:
            if settings['starttls']:
                client.starttls(context=ssl.create_default_context())
            if settings.get('username'):
                client.login(settings['username'], settings.get('password', ''))
            client.send_message(message)
        return 'sent'
    except (OSError, smtplib.SMTPException):
        current_app.logger.warning('Notification de page non envoyée.')
        return 'failed'
