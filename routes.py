import logging
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from app import db
from models import User, Feed, Article, Draft, Newsletter, Subscriber
from services.scraper import fetch_rss_feed, fetch_website_content
from services.notion_client import save_to_notion, get_from_notion
from services.ai_generator import generate_newsletter_draft
from services.email_sender import send_newsletter
from services.telegram_notifier import send_notification
from utils.helpers import format_date, truncate_text, get_reading_time

logger = logging.getLogger(__name__)

def init_routes(app):
    
    # Authentication routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
            
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')
            
            user = User.query.filter_by(email=email).first()
            
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password', 'danger')
                
        return render_template('login.html')
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
            
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            
            # Check if user already exists
            existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
            if existing_user:
                flash('Username or email already exists', 'danger')
                return render_template('register.html')
            
            # Create new user
            new_user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
            
        return render_template('register.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
    # Main routes
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        # Get counts for dashboard
        feed_count = Feed.query.filter_by(user_id=current_user.id).count()
        article_count = Article.query.join(Feed).filter(Feed.user_id == current_user.id).count()
        draft_count = Draft.query.filter_by(user_id=current_user.id).count()
        newsletter_count = Newsletter.query.filter_by(user_id=current_user.id).count()
        
        # Get recent items
        recent_articles = (Article.query
                           .join(Feed)
                           .filter(Feed.user_id == current_user.id)
                           .order_by(Article.fetched_at.desc())
                           .limit(5)
                           .all())
        
        recent_drafts = (Draft.query
                         .filter_by(user_id=current_user.id)
                         .order_by(Draft.updated_at.desc())
                         .limit(5)
                         .all())
        
        recent_newsletters = (Newsletter.query
                              .filter_by(user_id=current_user.id)
                              .order_by(Newsletter.created_at.desc())
                              .limit(5)
                              .all())
        
        upcoming_newsletters = (Newsletter.query
                                .filter(Newsletter.user_id == current_user.id,
                                        Newsletter.status == 'scheduled',
                                        Newsletter.scheduled_for > datetime.utcnow())
                                .order_by(Newsletter.scheduled_for)
                                .limit(3)
                                .all())
        
        # Get statistics for engagement
        sent_newsletters = Newsletter.query.filter(
            Newsletter.user_id == current_user.id,
            Newsletter.status == 'sent'
        ).all()
        
        total_recipients = sum(n.recipient_count for n in sent_newsletters) if sent_newsletters else 0
        total_opens = sum(n.open_count for n in sent_newsletters) if sent_newsletters else 0
        total_clicks = sum(n.click_count for n in sent_newsletters) if sent_newsletters else 0
        
        open_rate = (total_opens / total_recipients * 100) if total_recipients > 0 else 0
        click_rate = (total_clicks / total_recipients * 100) if total_recipients > 0 else 0
        
        return render_template(
            'dashboard.html',
            feed_count=feed_count,
            article_count=article_count,
            draft_count=draft_count,
            newsletter_count=newsletter_count,
            recent_articles=recent_articles,
            recent_drafts=recent_drafts,
            recent_newsletters=recent_newsletters,
            upcoming_newsletters=upcoming_newsletters,
            open_rate=open_rate,
            click_rate=click_rate,
            total_recipients=total_recipients,
            format_date=format_date,
            truncate_text=truncate_text
        )
    
    # Feed routes
    @app.route('/feeds')
    @login_required
    def feeds():
        feeds = Feed.query.filter_by(user_id=current_user.id).order_by(Feed.created_at.desc()).all()
        return render_template('feeds.html', feeds=feeds, format_date=format_date)
    
    @app.route('/feeds/add', methods=['POST'])
    @login_required
    def add_feed():
        name = request.form.get('name')
        url = request.form.get('url')
        feed_type = request.form.get('type')
        
        if not name or not url or not feed_type:
            flash('Please fill all required fields', 'danger')
            return redirect(url_for('feeds'))
        
        new_feed = Feed(
            name=name,
            url=url,
            type=feed_type,
            user_id=current_user.id
        )
        
        db.session.add(new_feed)
        db.session.commit()
        
        # Try to fetch content immediately
        try:
            if feed_type == 'rss':
                articles = fetch_rss_feed(new_feed)
            else:
                articles = fetch_website_content(new_feed)
                
            if articles:
                new_feed.last_fetched = datetime.utcnow()
                db.session.commit()
                flash(f'Successfully added feed and fetched {len(articles)} articles', 'success')
            else:
                flash('Added feed but could not fetch articles', 'warning')
        except Exception as e:
            logger.error(f"Error fetching feed content: {str(e)}")
            flash(f'Added feed but error fetching content: {str(e)}', 'warning')
        
        return redirect(url_for('feeds'))
    
    @app.route('/feeds/<int:feed_id>/delete', methods=['POST'])
    @login_required
    def delete_feed(feed_id):
        feed = Feed.query.filter_by(id=feed_id, user_id=current_user.id).first_or_404()
        
        db.session.delete(feed)
        db.session.commit()
        
        flash('Feed deleted successfully', 'success')
        return redirect(url_for('feeds'))
    
    @app.route('/feeds/<int:feed_id>/fetch', methods=['POST'])
    @login_required
    def fetch_feed(feed_id):
        feed = Feed.query.filter_by(id=feed_id, user_id=current_user.id).first_or_404()
        
        try:
            if feed.type == 'rss':
                articles = fetch_rss_feed(feed)
            else:
                articles = fetch_website_content(feed)
                
            if articles:
                feed.last_fetched = datetime.utcnow()
                db.session.commit()
                flash(f'Successfully fetched {len(articles)} articles', 'success')
            else:
                flash('No new articles found', 'info')
        except Exception as e:
            logger.error(f"Error fetching feed content: {str(e)}")
            flash(f'Error fetching content: {str(e)}', 'danger')
        
        return redirect(url_for('feeds'))
    
    @app.route('/articles')
    @login_required
    def articles():
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        articles_query = (Article.query
                         .join(Feed)
                         .filter(Feed.user_id == current_user.id)
                         .order_by(Article.fetched_at.desc()))
        
        # Filter options
        feed_id = request.args.get('feed_id', type=int)
        if feed_id:
            articles_query = articles_query.filter(Article.feed_id == feed_id)
            
        unused_only = request.args.get('unused_only') == 'true'
        if unused_only:
            articles_query = articles_query.filter(Article.used_in_draft == False)
            
        pagination = articles_query.paginate(page=page, per_page=per_page)
        
        feeds = Feed.query.filter_by(user_id=current_user.id).all()
        
        return render_template(
            'articles.html', 
            articles=pagination.items,
            pagination=pagination,
            feeds=feeds,
            current_feed_id=feed_id,
            unused_only=unused_only,
            format_date=format_date,
            truncate_text=truncate_text,
            get_reading_time=get_reading_time
        )
    
    # Drafts routes
    @app.route('/drafts')
    @login_required
    def drafts():
        drafts = Draft.query.filter_by(user_id=current_user.id).order_by(Draft.updated_at.desc()).all()
        return render_template('drafts.html', drafts=drafts, format_date=format_date)
    
    @app.route('/drafts/new', methods=['GET', 'POST'])
    @login_required
    def new_draft():
        if request.method == 'POST':
            title = request.form.get('title')
            content = request.form.get('content')
            
            if not title or not content:
                flash('Please provide both title and content', 'danger')
                return render_template('draft_editor.html', title=title, content=content)
            
            new_draft = Draft(
                title=title,
                content=content,
                user_id=current_user.id
            )
            
            db.session.add(new_draft)
            db.session.commit()
            
            # Save to Notion if API key is set
            if current_user.notion_api_key:
                try:
                    notion_page_id = save_to_notion(new_draft, current_user.notion_api_key)
                    if notion_page_id:
                        new_draft.notion_page_id = notion_page_id
                        db.session.commit()
                        flash('Draft saved to Notion', 'success')
                except Exception as e:
                    logger.error(f"Error saving to Notion: {str(e)}")
                    flash(f'Error saving to Notion: {str(e)}', 'warning')
            
            flash('Draft created successfully', 'success')
            return redirect(url_for('drafts'))
            
        # Selected articles for inclusion in the draft
        article_ids = request.args.getlist('article_ids', type=int)
        selected_articles = []
        
        if article_ids:
            selected_articles = (Article.query
                               .join(Feed)
                               .filter(Article.id.in_(article_ids), Feed.user_id == current_user.id)
                               .all())
        
        return render_template('draft_editor.html', articles=selected_articles)
    
    @app.route('/drafts/generate', methods=['POST'])
    @login_required
    def generate_draft():
        article_ids = request.form.getlist('article_ids', type=int)
        
        if not article_ids:
            flash('Please select at least one article to generate a draft', 'danger')
            return redirect(url_for('articles'))
        
        articles = (Article.query
                  .join(Feed)
                  .filter(Article.id.in_(article_ids), Feed.user_id == current_user.id)
                  .all())
        
        if not articles:
            flash('No valid articles found', 'danger')
            return redirect(url_for('articles'))
        
        try:
            title, content = generate_newsletter_draft(articles)
            
            # Mark articles as used
            for article in articles:
                article.used_in_draft = True
            
            # Create the draft
            new_draft = Draft(
                title=title,
                content=content,
                user_id=current_user.id
            )
            
            db.session.add(new_draft)
            db.session.commit()
            
            # Save to Notion if API key is set
            if current_user.notion_api_key:
                try:
                    notion_page_id = save_to_notion(new_draft, current_user.notion_api_key)
                    if notion_page_id:
                        new_draft.notion_page_id = notion_page_id
                        db.session.commit()
                except Exception as e:
                    logger.error(f"Error saving to Notion: {str(e)}")
                    flash(f'Draft created but error saving to Notion: {str(e)}', 'warning')
            
            flash('Draft generated successfully', 'success')
            return redirect(url_for('edit_draft', draft_id=new_draft.id))
        
        except Exception as e:
            logger.error(f"Error generating draft: {str(e)}")
            flash(f'Error generating draft: {str(e)}', 'danger')
            return redirect(url_for('articles'))
    
    @app.route('/drafts/<int:draft_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_draft(draft_id):
        draft = Draft.query.filter_by(id=draft_id, user_id=current_user.id).first_or_404()
        
        if request.method == 'POST':
            title = request.form.get('title')
            content = request.form.get('content')
            
            if not title or not content:
                flash('Please provide both title and content', 'danger')
                return render_template('draft_editor.html', draft=draft)
            
            draft.title = title
            draft.content = content
            draft.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Update in Notion if connected
            if draft.notion_page_id and current_user.notion_api_key:
                try:
                    save_to_notion(draft, current_user.notion_api_key, draft.notion_page_id)
                    flash('Draft updated in Notion', 'success')
                except Exception as e:
                    logger.error(f"Error updating Notion: {str(e)}")
                    flash(f'Error updating Notion: {str(e)}', 'warning')
            
            flash('Draft updated successfully', 'success')
            return redirect(url_for('drafts'))
            
        return render_template('draft_editor.html', draft=draft)
    
    @app.route('/drafts/<int:draft_id>/delete', methods=['POST'])
    @login_required
    def delete_draft(draft_id):
        draft = Draft.query.filter_by(id=draft_id, user_id=current_user.id).first_or_404()
        
        db.session.delete(draft)
        db.session.commit()
        
        flash('Draft deleted successfully', 'success')
        return redirect(url_for('drafts'))
    
    @app.route('/drafts/<int:draft_id>/sync-from-notion', methods=['POST'])
    @login_required
    def sync_from_notion(draft_id):
        draft = Draft.query.filter_by(id=draft_id, user_id=current_user.id).first_or_404()
        
        if not draft.notion_page_id or not current_user.notion_api_key:
            flash('This draft is not connected to Notion', 'danger')
            return redirect(url_for('edit_draft', draft_id=draft_id))
        
        try:
            title, content = get_from_notion(draft.notion_page_id, current_user.notion_api_key)
            
            if title and content:
                draft.title = title
                draft.content = content
                draft.updated_at = datetime.utcnow()
                db.session.commit()
                
                flash('Draft synchronized from Notion', 'success')
            else:
                flash('Could not retrieve content from Notion', 'warning')
                
        except Exception as e:
            logger.error(f"Error syncing from Notion: {str(e)}")
            flash(f'Error syncing from Notion: {str(e)}', 'danger')
            
        return redirect(url_for('edit_draft', draft_id=draft_id))
    
    # Newsletter routes
    @app.route('/newsletters')
    @login_required
    def newsletters():
        status_filter = request.args.get('status')
        
        query = Newsletter.query.filter_by(user_id=current_user.id)
        
        if status_filter:
            query = query.filter_by(status=status_filter)
            
        newsletters = query.order_by(Newsletter.created_at.desc()).all()
        
        return render_template('newsletters.html', newsletters=newsletters, format_date=format_date)
    
    @app.route('/newsletters/schedule', methods=['GET', 'POST'])
    @login_required
    def schedule_newsletter():
        if request.method == 'POST':
            draft_id = request.form.get('draft_id', type=int)
            subject = request.form.get('subject')
            scheduled_date = request.form.get('scheduled_date')
            scheduled_time = request.form.get('scheduled_time')
            
            if not draft_id or not subject or not scheduled_date or not scheduled_time:
                flash('Please fill all required fields', 'danger')
                return redirect(url_for('schedule_newsletter'))
            
            # Parse the scheduled date and time
            try:
                scheduled_datetime = datetime.strptime(
                    f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                flash('Invalid date or time format', 'danger')
                return redirect(url_for('schedule_newsletter'))
            
            draft = Draft.query.filter_by(id=draft_id, user_id=current_user.id).first()
            if not draft:
                flash('Selected draft not found', 'danger')
                return redirect(url_for('schedule_newsletter'))
            
            newsletter = Newsletter(
                subject=subject,
                scheduled_for=scheduled_datetime,
                user_id=current_user.id,
                draft_id=draft_id
            )
            
            # Update draft status
            draft.status = 'scheduled'
            
            db.session.add(newsletter)
            db.session.commit()
            
            # Send notification if configured
            if current_user.telegram_chat_id and current_user.telegram_bot_token:
                try:
                    message = f"Newsletter '{subject}' scheduled for {scheduled_datetime.strftime('%Y-%m-%d %H:%M')}"
                    send_notification(current_user.telegram_bot_token, current_user.telegram_chat_id, message)
                except Exception as e:
                    logger.error(f"Error sending Telegram notification: {str(e)}")
            
            flash('Newsletter scheduled successfully', 'success')
            return redirect(url_for('newsletters'))
        
        # Get available drafts for scheduling
        drafts = Draft.query.filter_by(user_id=current_user.id, status='draft').all()
        
        return render_template('schedule_newsletter.html', drafts=drafts)
    
    @app.route('/newsletters/<int:newsletter_id>/send', methods=['POST'])
    @login_required
    def send_newsletter_now(newsletter_id):
        newsletter = Newsletter.query.filter_by(id=newsletter_id, user_id=current_user.id).first_or_404()
        
        if newsletter.status not in ['scheduled', 'failed']:
            flash('This newsletter cannot be sent now', 'danger')
            return redirect(url_for('newsletters'))
        
        # Get subscribers
        subscribers = Subscriber.query.filter_by(user_id=current_user.id, is_active=True).all()
        
        if not subscribers:
            flash('You have no active subscribers', 'warning')
            return redirect(url_for('newsletters'))
        
        # Update newsletter status
        newsletter.status = 'sending'
        db.session.commit()
        
        try:
            # Send the newsletter
            success, error = send_newsletter(
                newsletter,
                newsletter.draft.content,
                subscribers,
                current_user.sendgrid_api_key
            )
            
            if success:
                newsletter.status = 'sent'
                newsletter.sent_at = datetime.utcnow()
                newsletter.recipient_count = len(subscribers)
                
                # Update draft status
                newsletter.draft.status = 'published'
                
                db.session.commit()
                
                # Send notification if configured
                if current_user.telegram_chat_id and current_user.telegram_bot_token:
                    try:
                        message = f"Newsletter '{newsletter.subject}' sent to {len(subscribers)} subscribers"
                        send_notification(current_user.telegram_bot_token, current_user.telegram_chat_id, message)
                    except Exception as e:
                        logger.error(f"Error sending Telegram notification: {str(e)}")
                
                flash(f'Newsletter sent to {len(subscribers)} subscribers', 'success')
            else:
                newsletter.status = 'failed'
                newsletter.error_message = error
                db.session.commit()
                
                flash(f'Failed to send newsletter: {error}', 'danger')
                
        except Exception as e:
            logger.error(f"Error sending newsletter: {str(e)}")
            newsletter.status = 'failed'
            newsletter.error_message = str(e)
            db.session.commit()
            
            flash(f'Error sending newsletter: {str(e)}', 'danger')
            
        return redirect(url_for('newsletters'))
    
    @app.route('/newsletters/<int:newsletter_id>/cancel', methods=['POST'])
    @login_required
    def cancel_newsletter(newsletter_id):
        newsletter = Newsletter.query.filter_by(id=newsletter_id, user_id=current_user.id).first_or_404()
        
        if newsletter.status != 'scheduled':
            flash('Only scheduled newsletters can be cancelled', 'danger')
            return redirect(url_for('newsletters'))
        
        # Get the draft and reset its status
        draft = newsletter.draft
        draft.status = 'draft'
        
        # Delete the newsletter
        db.session.delete(newsletter)
        db.session.commit()
        
        flash('Newsletter cancelled successfully', 'success')
        return redirect(url_for('newsletters'))
    
    # Subscriber routes
    @app.route('/subscribers')
    @login_required
    def subscribers():
        subscribers = Subscriber.query.filter_by(user_id=current_user.id).order_by(Subscriber.created_at.desc()).all()
        return render_template('subscribers.html', subscribers=subscribers, format_date=format_date)
    
    @app.route('/subscribers/add', methods=['POST'])
    @login_required
    def add_subscriber():
        email = request.form.get('email')
        name = request.form.get('name', '')
        
        if not email:
            flash('Email is required', 'danger')
            return redirect(url_for('subscribers'))
        
        # Check if subscriber already exists
        existing = Subscriber.query.filter_by(email=email, user_id=current_user.id).first()
        if existing:
            flash('This email is already in your subscriber list', 'warning')
            return redirect(url_for('subscribers'))
        
        new_subscriber = Subscriber(
            email=email,
            name=name,
            user_id=current_user.id
        )
        
        db.session.add(new_subscriber)
        db.session.commit()
        
        flash('Subscriber added successfully', 'success')
        return redirect(url_for('subscribers'))
    
    @app.route('/subscribers/<int:subscriber_id>/toggle', methods=['POST'])
    @login_required
    def toggle_subscriber(subscriber_id):
        subscriber = Subscriber.query.filter_by(id=subscriber_id, user_id=current_user.id).first_or_404()
        
        subscriber.is_active = not subscriber.is_active
        db.session.commit()
        
        status = 'activated' if subscriber.is_active else 'deactivated'
        flash(f'Subscriber {status} successfully', 'success')
        return redirect(url_for('subscribers'))
    
    @app.route('/subscribers/<int:subscriber_id>/delete', methods=['POST'])
    @login_required
    def delete_subscriber(subscriber_id):
        subscriber = Subscriber.query.filter_by(id=subscriber_id, user_id=current_user.id).first_or_404()
        
        db.session.delete(subscriber)
        db.session.commit()
        
        flash('Subscriber deleted successfully', 'success')
        return redirect(url_for('subscribers'))
    
    # Settings route
    @app.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings():
        if request.method == 'POST':
            # Update integration settings
            notion_api_key = request.form.get('notion_api_key')
            sendgrid_api_key = request.form.get('sendgrid_api_key')
            telegram_bot_token = request.form.get('telegram_bot_token')
            telegram_chat_id = request.form.get('telegram_chat_id')
            
            current_user.notion_api_key = notion_api_key
            current_user.sendgrid_api_key = sendgrid_api_key
            current_user.telegram_bot_token = telegram_bot_token
            current_user.telegram_chat_id = telegram_chat_id
            
            # Handle password change
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if current_password and new_password and confirm_password:
                if not check_password_hash(current_user.password_hash, current_password):
                    flash('Current password is incorrect', 'danger')
                    return redirect(url_for('settings'))
                    
                if new_password != confirm_password:
                    flash('New passwords do not match', 'danger')
                    return redirect(url_for('settings'))
                    
                current_user.password_hash = generate_password_hash(new_password)
                flash('Password updated successfully', 'success')
            
            db.session.commit()
            flash('Settings updated successfully', 'success')
            return redirect(url_for('settings'))
            
        return render_template('settings.html')
    
    # API route for checking scheduled newsletters
    @app.route('/api/check-scheduled', methods=['POST'])
    def check_scheduled_newsletters():
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != os.environ.get('SCHEDULER_API_KEY'):
            return jsonify({'error': 'Unauthorized'}), 401
        
        now = datetime.utcnow()
        
        # Find newsletters that are scheduled and due
        due_newsletters = Newsletter.query.filter(
            Newsletter.status == 'scheduled',
            Newsletter.scheduled_for <= now
        ).all()
        
        results = []
        
        for newsletter in due_newsletters:
            user = User.query.get(newsletter.user_id)
            subscribers = Subscriber.query.filter_by(user_id=user.id, is_active=True).all()
            
            if not subscribers:
                newsletter.status = 'failed'
                newsletter.error_message = 'No active subscribers'
                db.session.commit()
                results.append({
                    'id': newsletter.id,
                    'result': 'failed',
                    'reason': 'No active subscribers'
                })
                continue
            
            # Update status to sending
            newsletter.status = 'sending'
            db.session.commit()
            
            try:
                # Send the newsletter
                success, error = send_newsletter(
                    newsletter,
                    newsletter.draft.content,
                    subscribers,
                    user.sendgrid_api_key
                )
                
                if success:
                    newsletter.status = 'sent'
                    newsletter.sent_at = now
                    newsletter.recipient_count = len(subscribers)
                    
                    # Update draft status
                    newsletter.draft.status = 'published'
                    
                    db.session.commit()
                    
                    # Send notification if configured
                    if user.telegram_chat_id and user.telegram_bot_token:
                        try:
                            message = f"Newsletter '{newsletter.subject}' sent to {len(subscribers)} subscribers"
                            send_notification(user.telegram_bot_token, user.telegram_chat_id, message)
                        except Exception as e:
                            logger.error(f"Error sending Telegram notification: {str(e)}")
                    
                    results.append({
                        'id': newsletter.id,
                        'result': 'sent',
                        'recipients': len(subscribers)
                    })
                else:
                    newsletter.status = 'failed'
                    newsletter.error_message = error
                    db.session.commit()
                    
                    results.append({
                        'id': newsletter.id,
                        'result': 'failed',
                        'reason': error
                    })
                    
            except Exception as e:
                logger.error(f"Error sending scheduled newsletter: {str(e)}")
                newsletter.status = 'failed'
                newsletter.error_message = str(e)
                db.session.commit()
                
                results.append({
                    'id': newsletter.id,
                    'result': 'failed',
                    'reason': str(e)
                })
        
        return jsonify({
            'processed': len(results),
            'results': results
        })
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def server_error(e):
        return render_template('500.html'), 500
