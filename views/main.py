from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user
from models.content import Content
from sqlalchemy import desc
import logging # Added for debugging
from extensions import db # Corrected import for db
from datetime import timezone # Import timezone

# Create a blueprint for main routes
bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    # Expire all instances to ensure fresh data from DB
    db.session.expire_all()
    
    # Get the first page of content items
    content_items_query = Content.query.order_by(desc(Content.created_at)).limit(12).all()
    
    # Make created_at timezone-aware for template rendering
    content_items = []
    for item in content_items_query:
        if item.created_at:
            item.created_at = item.created_at.replace(tzinfo=timezone.utc)
        # Assuming publish_date might also be naive UTC and needs similar handling if displayed directly in Jinja
        if item.publish_date: # Add this block if publish_date is also naive UTC
            item.publish_date = item.publish_date.replace(tzinfo=timezone.utc)
        content_items.append(item)
    
    has_more_content = Content.query.count() > 12
    
    # Debugging: Log the fetched content items, especially the excerpt of item 1 if it exists
    if content_items:
        for item in content_items:
            if item.id == 1: # Assuming you are testing with content_id = 1 as per logs
                logging.info(f"Index route: Fetched content id 1 with excerpt: '{item.excerpt}'")
            # You might want to log all items or be more specific based on your testing
    else:
        logging.info("Index route: No content items fetched.")
    
    return render_template('index.html', 
                         content_items=content_items,
                         has_more_content=has_more_content)

@bp.route('/api/content')
def get_content():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    # Get paginated content items
    content_items = Content.query.order_by(desc(Content.created_at))\
        .offset((page - 1) * per_page)\
        .limit(per_page + 1)\
        .all()
    
    # Check if there are more items
    has_more = len(content_items) > per_page
    if has_more:
        content_items = content_items[:-1]
    
    # Convert items to dict for JSON response
    items = [{
        'id': item.id,
        'title': item.title,
        'content_type': item.content_type,
        'url': item.url,
        'excerpt': item.excerpt,
        'image_url': item.image_url,
        'author': item.author,
        'publish_date': item.publish_date.isoformat() if item.publish_date else None,
        'created_at': item.created_at.isoformat()
    } for item in content_items]
    
    return jsonify({
        'content': items,
        'has_more': has_more
    })

@bp.route('/api/promote', methods=['POST'])
def promote_content():
    data = request.get_json()
    content_id = data.get('content_id')
    content_type = data.get('content_type')
    title = data.get('title')
    description = data.get('description')
    
    if not all([content_id, content_type, title, description]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        # Get the content item
        content = Content.query.get(content_id)
        if not content:
            return jsonify({'error': 'Content not found'}), 404
        
        # TODO: Implement promotion logic here
        # For now, just return success
        return jsonify({'message': 'Content promoted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
