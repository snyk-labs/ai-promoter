"""
Content model for all types of content (articles, videos, podcasts, etc.).
"""

from datetime import datetime
from extensions import db
from models.user import User
from models.share import Share
from flask import current_app
from sqlalchemy import event
from urllib.parse import urlparse, parse_qs, urlencode
import re


class Content(db.Model):
    __tablename__ = "content"

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.Text, nullable=False, unique=True)
    title = db.Column(db.Text, nullable=False)
    scraped_content = db.Column(
        db.Text, nullable=True
    )  # Raw markdown content from Firecrawl
    excerpt = db.Column(db.Text, nullable=True)
    copy = db.Column(db.Text, nullable=True)  # Exact body for social posts
    image_url = db.Column(db.Text, nullable=True)
    publish_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    context = db.Column(
        db.Text, nullable=True
    )  # Additional context for social media posts
    utm_campaign = db.Column(
        db.Text, nullable=True
    )  # UTM campaign parameter for content promotion
    submitted_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_content_submitted_by_id_users"),
        nullable=True,
    )
    submitted_by = db.relationship(
        "User", backref=db.backref("submitted_content", lazy=True)
    )

    # Relationship with Share model using back_populates
    shares = db.relationship(
        "Share", back_populates="content", lazy="dynamic", cascade="all, delete-orphan"
    )

    def _parse_utm_params(self, url_string):
        """
        Parse UTM parameters from a URL string.
        Returns the base URL (with non-UTM params) and a dict of UTM params.
        """
        parsed_url = urlparse(url_string)
        query_params = parse_qs(parsed_url.query)

        utm_params_dict = {}
        non_utm_params_dict = {}

        for k, v_list in query_params.items():
            if not v_list:
                continue  # Should not happen with parse_qs normally
            value = v_list[0]
            if k.startswith("utm_"):
                utm_params_dict[k] = value
            else:
                non_utm_params_dict[k] = value

        base_url_path = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        if non_utm_params_dict:
            return f"{base_url_path}?{urlencode(non_utm_params_dict)}", utm_params_dict
        return base_url_path, utm_params_dict

    def _merge_utm_params(self, existing_params, new_params):
        """
        Merge UTM parameters, with new_params overriding existing_params.
        """
        merged = existing_params.copy()
        merged.update(new_params)
        return merged

    def _build_url_with_utm(self, base_url, utm_params_dict):
        """
        Build a full URL by appending UTM parameters to a base URL.
        """
        if not utm_params_dict:
            return base_url

        utm_query_string = urlencode(utm_params_dict)
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{utm_query_string}"

    def _get_url_with_final_utms(self, url_string, master_utms_to_apply):
        """
        Takes a URL string, parses it, merges its existing UTMs with master_utms_to_apply
        (master_utms_to_apply taking precedence), and returns the rebuilt URL.
        """
        base_url_part, existing_utms_on_url = self._parse_utm_params(url_string)
        final_utms_for_this_url = self._merge_utm_params(
            existing_utms_on_url, master_utms_to_apply
        )
        return self._build_url_with_utm(base_url_part, final_utms_for_this_url)

    def get_url_with_all_utms(self):
        """
        Returns the content's primary URL (self.url) with all UTM parameters correctly
        merged and applied (from app config, the URL itself, and self.utm_campaign).
        App config and self.utm_campaign parameters take precedence.
        """
        # 1. Prepare Desired UTMs (master set from config and instance)
        config_utm_string = current_app.config.get("UTM_PARAMS", "")
        if config_utm_string.startswith("?"):
            config_utm_string = config_utm_string[1:]

        desired_utms = {}
        if config_utm_string:
            parsed_config_params = parse_qs(config_utm_string)
            desired_utms = {k: v[0] for k, v in parsed_config_params.items() if v}

        if self.utm_campaign:
            desired_utms["utm_campaign"] = self.utm_campaign  # Add/override

        # 2. Use the _get_url_with_final_utms helper to apply these desired UTMs to self.url
        return self._get_url_with_final_utms(self.url, desired_utms)

    def process_copy_with_utm_params(self, copy_text):
        """
        Process copy text to ensure it includes the content URL with correctly
        merged and deduplicated UTM parameters.
        """
        if copy_text is None:  # Handle None copy_text explicitly
            copy_text = ""

        # 1. Prepare Desired UTMs (master set from config and instance)
        config_utm_string = current_app.config.get("UTM_PARAMS", "")
        if config_utm_string.startswith("?"):
            config_utm_string = config_utm_string[1:]  # Strip leading '?'

        desired_utms = {}
        if config_utm_string:
            parsed_config_params = parse_qs(config_utm_string)
            desired_utms = {k: v[0] for k, v in parsed_config_params.items() if v}

        if self.utm_campaign:
            desired_utms["utm_campaign"] = self.utm_campaign  # Add/override

        # 2. Determine the canonical version of self.url (content's main URL)
        canonical_url_with_utms = self._get_url_with_final_utms(self.url, desired_utms)

        # 3. Process copy_text: Find and update URLs within it
        parsed_main_content_url = urlparse(self.url)
        main_content_url_base_path = f"{parsed_main_content_url.scheme}://{parsed_main_content_url.netloc}{parsed_main_content_url.path}"
        escaped_base_url_path_for_regex = re.escape(main_content_url_base_path)
        url_pattern_in_copy = rf"({escaped_base_url_path_for_regex}[^\s\"'<]*)"

        found_url_in_copy_flag = False

        def replace_url_in_copy_match(match_obj):
            nonlocal found_url_in_copy_flag
            found_url_in_copy_flag = True

            url_found_in_copy_text = match_obj.group(1)

            # Parse this specific URL found in the copy to separate its base and its own UTMs
            base_of_url_in_copy, utms_of_url_in_copy = self._parse_utm_params(
                url_found_in_copy_text
            )

            # Merge the UTMs from the URL in copy with our desired UTMs (desired take precedence)
            final_utms_for_this_url_in_copy = self._merge_utm_params(
                utms_of_url_in_copy, desired_utms
            )

            # Rebuild this specific URL with the final merged UTMs
            return self._get_url_with_final_utms(
                base_of_url_in_copy, final_utms_for_this_url_in_copy
            )

        modified_copy_text = re.sub(
            url_pattern_in_copy, replace_url_in_copy_match, copy_text
        )

        if not found_url_in_copy_flag:
            # If no URL matching the content's base URL was found and replaced in the copy text,
            # append the canonical URL (with all desired UTMs) to the copy text.
            separator = (
                " "
                if modified_copy_text and not modified_copy_text.endswith(" ")
                else ""
            )
            modified_copy_text = (
                f"{modified_copy_text}{separator}{canonical_url_with_utms}"
            )

        return modified_copy_text

    @property
    def share_count(self):
        """Get the total number of shares for this content."""
        return self.shares.count()

    @property
    def platform_share_counts(self):
        """Get share counts broken down by platform for this content."""
        from sqlalchemy import func

        return (
            db.session.query(Share.platform, func.count(Share.id).label("count"))
            .filter_by(content_id=self.id)
            .group_by(Share.platform)
            .all()
        )

    def __repr__(self):
        return f"<Content {self.id}: {self.title}>"

    def delete(self):
        """Delete the content item from the database."""
        db.session.delete(self)
        db.session.commit()


@event.listens_for(Content, "before_insert")
@event.listens_for(Content, "before_update")
def process_copy_before_save(mapper, connection, target):
    """Process the copy text with UTM parameters before saving the content."""
    # Ensure target.copy is processed only if it's not None.
    # The process_copy_with_utm_params method now handles None by returning ""
    if target.copy:
        target.copy = target.process_copy_with_utm_params(target.copy)
