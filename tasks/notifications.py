from datetime import datetime, timedelta
from celery import shared_task
from flask import current_app
from models import User, Content
from extensions import db, redis_client
from flask_mail import Message
from extensions import mail

@shared_task
def initiate_posts():
    """
    Periodic task that runs three times per day to notify users about new content.
    Checks for content added since the last run and sends emails to users with social connections.
    """
    # Get the last run time from Redis or default to 24 hours ago
    last_run = redis_client.get('last_content_notification_run')
    if last_run:
        last_run = datetime.fromisoformat(last_run)
    else:
        last_run = datetime.utcnow() - timedelta(hours=24)

    # Find new content since last run
    new_content = Content.query.filter(Content.created_at > last_run).all()

    # If no new content, return early
    if not new_content:
        return "No new content to notify about"

    # Get users with LinkedIn authorization
    users = User.query.filter(User.linkedin_authorized == True).all()

    # Prepare content summary
    content_summary = []
    
    for item in new_content:
        content_summary.append({
            'id': item.id,
            'type': 'content',
            'title': item.title,
            'url': item.url,
            'description': item.excerpt or item.scraped_content[:200] + '...',
            'image_url': item.image_url
        })

    # Send emails to users
    for user in users:
        msg = Message(
            subject="New Content Available to Share!",
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            recipients=[user.email]
        )
        
        # Create email content
        html_content = f"""
        <h2>Hi {user.name},</h2>
        <p>We have new content available for you to share on your social media!</p>
        """
        
        for item in content_summary:
            html_content += f"""
            <div style="margin: 20px 0; padding: 15px; border: 1px solid #eee; border-radius: 5px;">
                <h3>{item['title']}</h3>
                <p>{item['description']}</p>
                <a href="{current_app.config['BASE_URL']}/?promote={item['id']}" 
                   style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">
                    Share This Content
                </a>
            </div>
            """
        
        msg.html = html_content
        mail.send(msg)

    # Update last run time
    redis_client.set(
        'last_content_notification_run',
        datetime.utcnow().isoformat()
    )

    return f"Sent notifications to {len(users)} users about {len(content_summary)} new content items" 