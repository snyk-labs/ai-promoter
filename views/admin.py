from functools import wraps
from flask import Blueprint, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required
from models.content import Content
from extensions import db
from tasks.content import scrape_content_task
from celery.result import AsyncResult
import logging

logger = logging.getLogger(__name__)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    """Decorator to require admin access for a route."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            if (
                request.accept_mimetypes.accept_json
                and not request.accept_mimetypes.accept_html
            ):
                return jsonify(error="Admin access required."), 403
            flash("You must be an admin to access this page.", "error")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)

    return decorated_function


@bp.route("/content/create", methods=["POST"])
@login_required
@admin_required
def create_content():
    """Create new content and trigger async scraping. Returns JSON with task_id."""
    url = request.form.get("url")
    context = request.form.get("context")
    copy = request.form.get("copy")
    utm_campaign = request.form.get("utm_campaign")

    if not url:
        return jsonify(error="URL is required."), 400

    existing_content = Content.query.filter_by(url=url).first()
    if existing_content:
        return jsonify(error="This URL has already been added as content."), 409

    try:
        content = Content(
            url=url,
            title="Processing...",  # Initial title
            context=context,
            copy=copy,  # The model will automatically process this with UTM parameters
            utm_campaign=utm_campaign,
            submitted_by_id=current_user.id,
        )
        db.session.add(content)
        db.session.commit()

        task = scrape_content_task.delay(content.id, url)

        return (
            jsonify(
                task_id=task.id,
                message="Content processing started.",
                content_id=content.id,
            ),
            202,
        )
    except Exception as e:
        logger.exception("Unexpected error while adding content")
        db.session.rollback()
        return jsonify(error=f"Error creating content: {str(e)}"), 500


@bp.route("/task_status/<task_id>", methods=["GET"])
@login_required
@admin_required
def task_status(task_id):
    """Check the status of a Celery task."""
    logger.info(f"Checking task status for task_id: {task_id}")
    task = scrape_content_task.AsyncResult(task_id)

    response_data = {
        "task_id": task_id,
        "status": task.state,  # Default to task.state, even if None
    }

    try:
        logger.debug(f"Task {task_id} state: {task.state}")

        if task.state == "PENDING":
            response_data["message"] = "Task is pending."
            logger.info(f"Task {task_id} is PENDING.")
        elif task.state == "FAILURE":
            response_data["message"] = str(
                task.info
            )  # task.info contains the exception
            logger.error(f"Task {task_id} FAILED. Info: {task.info}")
            # Attempt to get content even on failure, if task.result holds a content_id
            if task.result:
                try:
                    updated_content = Content.query.get(task.result)
                    if updated_content:
                        response_data["content"] = {
                            "id": updated_content.id,
                            "title": updated_content.title,
                            "url": updated_content.url,
                            "excerpt": updated_content.excerpt,
                            "image_url": updated_content.image_url,
                            "submitted_by_name": (
                                updated_content.submitted_by.name
                                if updated_content.submitted_by
                                else None
                            ),
                            "created_at_iso": updated_content.created_at.isoformat(),
                            "share_count": updated_content.share_count,
                            "platform_share_counts": [
                                {"platform": p.platform, "count": p.count}
                                for p in updated_content.platform_share_counts
                            ],
                            "utm_campaign": updated_content.utm_campaign,
                            "copy": updated_content.copy,
                            "context": updated_content.context,
                        }
                        logger.info(
                            f"Task {task_id} (FAILURE): Found content_id {task.result}"
                        )
                    else:
                        response_data["content_error"] = (
                            f"Content with ID {task.result} not found post-failure."
                        )
                        logger.warning(
                            f"Task {task_id} (FAILURE): Content with ID {task.result} not found."
                        )
                except Exception as e:
                    logger.exception(
                        f"Task {task_id} (FAILURE): Error retrieving content with ID {task.result}"
                    )
                    response_data["content_error"] = (
                        f"Error retrieving content: {str(e)}"
                    )
        elif task.state == "SUCCESS":
            response_data["message"] = "Task completed successfully."
            response_data["result"] = task.result
            logger.info(f"Task {task_id} SUCCEEDED. Result: {task.result}")
            if task.result:
                try:
                    updated_content = Content.query.get(task.result)
                    if updated_content:
                        response_data["content"] = {
                            "id": updated_content.id,
                            "title": updated_content.title,
                            "url": updated_content.url,
                            "excerpt": updated_content.excerpt,
                            "image_url": updated_content.image_url,
                            "submitted_by_name": (
                                updated_content.submitted_by.name
                                if updated_content.submitted_by
                                else None
                            ),
                            "created_at_iso": updated_content.created_at.isoformat(),
                            "share_count": updated_content.share_count,
                            "platform_share_counts": [
                                {"platform": p.platform, "count": p.count}
                                for p in updated_content.platform_share_counts
                            ],
                            "utm_campaign": updated_content.utm_campaign,
                            "copy": updated_content.copy,
                            "context": updated_content.context,
                        }
                        logger.info(
                            f"Task {task_id} (SUCCESS): Found content_id {task.result}"
                        )
                    else:
                        response_data["content_error"] = (
                            f"Content with ID {task.result} not found post-success."
                        )
                        logger.warning(
                            f"Task {task_id} (SUCCESS): Content with ID {task.result} not found."
                        )
                except Exception as e:
                    logger.exception(
                        f"Task {task_id} (SUCCESS): Error retrieving content with ID {task.result}"
                    )
                    response_data["content_error"] = (
                        f"Error retrieving content: {str(e)}"
                    )

            if task.result and "content" not in response_data:
                try:
                    retrieved_content_id = int(task.result)
                    final_content = Content.query.get(retrieved_content_id)
                    if final_content:
                        response_data["content"] = {
                            "id": final_content.id,
                            "title": final_content.title,
                            "url": final_content.url,
                            "excerpt": final_content.excerpt,
                            "image_url": final_content.image_url,
                            "submitted_by_name": (
                                final_content.submitted_by.name
                                if final_content.submitted_by
                                else None
                            ),
                            "created_at_iso": final_content.created_at.isoformat(),
                            "share_count": final_content.share_count,
                            "platform_share_counts": [
                                {"platform": p.platform, "count": p.count}
                                for p in final_content.platform_share_counts
                            ],
                            "utm_campaign": final_content.utm_campaign,
                            "copy": final_content.copy,
                            "context": final_content.context,
                        }
                        logger.info(
                            f"Task {task_id} (SUCCESS): Found content_id {retrieved_content_id}"
                        )
                    else:
                        response_data["content_error"] = (
                            f"Content with ID {retrieved_content_id} not found post-success."
                        )
                        logger.warning(
                            f"Task {task_id} (SUCCESS): Content with ID {retrieved_content_id} not found."
                        )
                except Exception as e:
                    logger.exception(
                        f"Task {task_id} (SUCCESS): Error retrieving content with ID {retrieved_content_id}"
                    )
                    response_data["content_error"] = (
                        f"Error retrieving content: {str(e)}"
                    )
        else:
            response_data["message"] = f"Task is in an unknown state: {task.state}"
            logger.warning(
                f"Task {task_id} is in an UNKNOWN state: {task.state}. Info: {task.info}"
            )

    except Exception as e:
        logger.exception(f"Unexpected error in task_status for task_id {task_id}")
        response_data["status"] = "ERROR"
        response_data["message"] = f"An server error occurred: {str(e)}"
        return jsonify(response_data), 500

    logger.debug(f"Returning task_status response for {task_id}: {response_data}")
    return jsonify(response_data)
