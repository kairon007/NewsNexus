from datetime import datetime
from app import db
from flask_login import UserMixin


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # User settings
    notion_api_key = db.Column(db.String(256))
    sendgrid_api_key = db.Column(db.String(256))
    telegram_chat_id = db.Column(db.String(64))
    telegram_bot_token = db.Column(db.String(256))
    
    # Relationships
    feeds = db.relationship('Feed', backref='user', lazy=True, cascade="all, delete-orphan")
    drafts = db.relationship('Draft', backref='user', lazy=True, cascade="all, delete-orphan")
    newsletters = db.relationship('Newsletter', backref='user', lazy=True, cascade="all, delete-orphan")


class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    url = db.Column(db.String(512), nullable=False)
    type = db.Column(db.String(32), nullable=False)  # 'rss' or 'website'
    last_fetched = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    articles = db.relationship('Article', backref='feed', lazy=True, cascade="all, delete-orphan")


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    url = db.Column(db.String(512), nullable=False)
    content = db.Column(db.Text)
    published_at = db.Column(db.DateTime)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    feed_id = db.Column(db.Integer, db.ForeignKey('feed.id'), nullable=False)
    used_in_draft = db.Column(db.Boolean, default=False)


class Draft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    content = db.Column(db.Text, nullable=False)
    notion_page_id = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = db.Column(db.String(32), default='draft')  # draft, published, scheduled
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    newsletter = db.relationship('Newsletter', backref='draft', lazy=True, uselist=False)


class Newsletter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(256), nullable=False)
    scheduled_for = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    recipient_count = db.Column(db.Integer, default=0)
    open_count = db.Column(db.Integer, default=0)
    click_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(32), default='scheduled')  # scheduled, sending, sent, failed
    error_message = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    draft_id = db.Column(db.Integer, db.ForeignKey('draft.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(128))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
