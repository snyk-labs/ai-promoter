# AI Promoter

[![Test Suite](https://github.com/snyk-labs/ai-promoter/actions/workflows/test.yml/badge.svg)](https://github.com/snyk-labs/ai-promoter/actions/workflows/test.yml) [![Coverage Status](https://coveralls.io/repos/github/snyk-labs/ai-promoter/badge.svg?branch=main)](https://coveralls.io/github/snyk-labs/ai-promoter?branch=main)

A Flask web application designed to help automate social media promotion for your content. This tool automatically syncs with podcast, blog, and YouTube RSS feeds, providing an interface for company employees to easily share new content on social media.

## Features

- Automatic content syncing from RSS feeds (podcasts, blogs, and YouTube videos)
- Clean, modern web interface for viewing content
- Items displayed with title, description, and publication date
- Direct links to original content
- Integration with Okta for single sign-on, or normal email/password authentication
- Automatically generates social media posts, taking each person's specific context into account
- Has a fully "autonomous" mode that allows for 100% automated social media promotion

## Project Architecture

This application follows the Model-View-Template (MVT) architecture pattern:

- **Models**: Defined in the `models/` package, representing the data structure. Key models include `User`, `Content`, and `Share`.
- **Views**: Located in the `views/` package, containing:
  - `main.py`: Main page routes
  - `api.py`: API endpoints for promotion
  - `auth.py`: Standard authentication routes
  - `okta_auth.py`: Okta SSO authentication routes
  - `admin.py`: Admin panel routes
- **Templates**: Stored in the `templates/` directory

The application is structured as follows:

- `app.py`: Application factory, configuration loading, extension initialization, blueprint registration, and Celery app initialization (`celery_init_app`).
- `config.py`: Centralized configuration class (`Config`) loading settings from environment variables. Defines configurations for Flask, database, Celery (including beat schedule), Okta, API keys, email, Slack, etc.
- `extensions.py`: Initializes and exports Flask extensions (SQLAlchemy `db`, Flask-Login `login_manager`, Flask-Migrate `migrate`, Flask-Mail `mail`, Flask-Redis `redis_client`).
- `celery_app.py`: Provides a Celery instance, primarily for CLI interactions. The main Celery app used by Flask is initialized in `app.py`.
- `models/`: Database models
  - `__init__.py`: Imports and exports all models
  - `user.py`: User model
  - `content.py`: Content model (for episodes, posts, videos)
  - `share.py`: Share model for tracking social media shares
- `views/`: View functions organized by feature, each blueprint typically in its own file.
  - `__init__.py`: Initializes and exports blueprints
  - `main.py`: Main application routes
  - `api.py`: API endpoints
  - `auth.py`: Authentication routes
  - `okta_auth.py`: Okta authentication routes
  - `admin.py`: Admin interface routes
- `cli/`: Command-line interface commands, registered in `app.py`.
  - `__init__.py`: Exports CLI command functions
  - `beat.py`: Celery beat scheduler command (`celery -A celery_app beat`) and a command to trigger content fetching.
  - `init_db.py`: Database initialization command (`flask init-db`)
  - `create_admin.py`: Command to create an admin user (`flask create-admin`)
  - `routes.py`: CLI command for listing application routes (`flask list-routes`)
- `helpers/`: Utility functions and modules, including Okta helpers and template helpers.
- `services/`: Modules for interacting with external services (e.g., Gemini, Firecrawl, LinkedIn).
- `tasks/`: Celery background tasks, organized by functionality.
  - `__init__.py`: Makes the tasks package importable.
  - `content.py`: Tasks related to content processing.
  - `fetch_content.py`: Task for fetching new content from RSS feeds.
  - `linkedin_tasks.py`: Tasks for LinkedIn integration (e.g., token refresh).
  - `notifications.py`: Tasks for sending notifications (e.g., initiating posts).
  - `promote.py`: Tasks for generating and posting social media content.
  - `slack_tasks.py`: Tasks for Slack integration.
- `static/`: Static assets (CSS, JS, images).
- `templates/`: HTML templates.
- `migrations/`: Database migration files generated by Flask-Migrate.

## Prerequisites

- Python 3.12
- pip (Python package installer)
- Virtual environment tool (venv)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Create a virtual environment:
```bash
# On macOS/Linux
python3.12 -m venv venv
source venv/bin/activate

# On Windows
python3.12 -m venv venv
venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Initialize the database:
```bash
# First, set the Flask application
export FLASK_APP=app.py  # On Windows: set FLASK_APP=app.py

# Then create the database tables
flask init-db
```

5. Set required environment variables

### Required Environment Variables

```bash
# Flask secret key (for session security)
export SECRET_KEY="your-secure-random-key"  # On Windows: set SECRET_KEY="your-secure-random-key"

# Gemini API Key (for generative AI features)
export GEMINI_API_KEY="your-gemini-api-key"

# LinkedIn Integration (required for social media posting)
export LINKEDIN_CLIENT_ID="your-linkedin-client-id"
export LINKEDIN_CLIENT_SECRET="your-linkedin-client-secret"

# Firecrawl API Key (for web scraping/content fetching)
export FIRECRAWL_API_KEY="your-firecrawl-api-key"

# Redis URL (for Celery broker and backend, and application caching)
export REDIS_URL="redis://localhost:6379/0" # Example, use your Redis instance URL

# Enable/disable Okta SSO (defaults to false)
export OKTA_ENABLED="false"  # Set to "true" to enable Okta SSO

# Company configuration
export COMPANY_NAME="Your Company Name"  # Displayed in the UI and page titles
export COMPANY_PRIVACY_NOTICE="<p>Your company privacy notice here. Can be HTML.</p>" # Displayed on relevant pages
export UTM_PARAMS="?utm_source=yourcompany.com&utm_medium=social"  # UTM parameters to append to all promoted URLs
export DASHBOARD_BANNER="<p>Custom HTML banner for non-admin users</p>"  # HTML content to display at the top of the dashboard

# Content Feeds (pipe-separated URLs for RSS feeds)
export CONTENT_FEEDS="https://feeds.simplecast.com/47yfLpm0|https://snyk.io/blog/feed/" # Example

# Email Configuration (enable with EMAIL_ENABLED="true")
export EMAIL_ENABLED="false"
export MAIL_SERVER="smtp.gmail.com"
export MAIL_PORT="587"
export MAIL_USE_TLS="true"
export MAIL_USERNAME="your-email@example.com"
export MAIL_PASSWORD="your-email-password"
export MAIL_DEFAULT_SENDER="AI Promoter <noreply@example.com>"

# Slack Configuration (enable with SLACK_NOTIFICATIONS_ENABLED="true")
export SLACK_NOTIFICATIONS_ENABLED="false"
export SLACK_BOT_TOKEN="xoxb-your-slack-bot-token"
export SLACK_DEFAULT_CHANNEL_ID="C123ABC456" # Default channel ID for notifications
```

The `DASHBOARD_BANNER` can contain any valid HTML and will be displayed at the top of the dashboard for non-admin users. For example:

```bash
export DASHBOARD_BANNER='<p class="font-bold">Important Notice</p><p>Please check out our new <a href="https://example.com" class="font-bold hover:underline">documentation</a> for the latest updates!</p>'
```

The `UTM_PARAMS` should be a query string that will be appended to all URLs in generated social media posts. For example:

```bash
export UTM_PARAMS="?utm_source=yourcompany.com&utm_medium=social&utm_campaign=promotion"
```

Note: The `UTM_PARAMS` can start with or without a `?` - the application will handle both formats correctly.

### Setting Up Okta SSO (Optional)

If you want to use Okta SSO for authentication, you'll need to set these additional variables:

```bash
# Okta application credentials
export OKTA_CLIENT_ID="your-okta-client-id"
export OKTA_CLIENT_SECRET="your-okta-client-secret"

# Okta domain with authorization server path
export OKTA_ISSUER="https://your-okta-domain.okta.com/oauth2/default"

# Redirect URI (must match what you set in Okta)
export OKTA_REDIRECT_URI="http://localhost:5000/auth/okta/callback"
```

See the [Okta SSO section](#setting-up-okta-sso-with-heroku) for details on setting up an Okta application.

## Usage

### Running the Web Application

1. Start the Flask development server:
```bash
python app.py
```

2. Open your browser and visit: http://localhost:5000

### Syncing Content from RSS Feeds

Content syncing from RSS feeds (defined by the `CONTENT_FEEDS` environment variable) is automated via a Celery Beat schedule. The `tasks.fetch_content.fetch_content_task` is scheduled to run hourly by default (see `CELERY` -> `beat_schedule` in `config.py`).

You can also trigger content fetching manually for testing or on-demand updates if needed.

#### Syncing Podcast Episodes (Manual Trigger Example)

To trigger a podcast sync manually (useful for development or immediate updates):

```bash
# First, ensure you're in your virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Set the Flask application
export FLASK_APP=app.py  # On Windows: set FLASK_APP=app.py

# Run the command to trigger content fetching (this will process all feeds in CONTENT_FEEDS)
flask trigger-fetch-content
```
This command leverages the `trigger_fetch_content_command` defined in `app.py`, which in turn uses functionality from `cli/beat.py` to dispatch the Celery task.

## Database

The application supports both SQLite (default for development) and PostgreSQL (recommended for production) databases.

### Database Configuration

By default, SQLite is used in development mode with the database file stored at `ai-promoter.db`. 

You can customize the database configuration using the `DATABASE_URL` environment variable:

```bash
# PostgreSQL configuration (recommended for production)
export DATABASE_URL="postgresql://username:password@localhost:5432/ai_promoter"

# Custom SQLite database path
export DATABASE_URL="sqlite:///path/to/your/custom.db"
```

### Database Initialization

To initialize the database for the first time:

```bash
# Set the Flask application
export FLASK_APP=app.py  # On Windows: set FLASK_APP=app.py

# Create the database tables
flask init-db
```

For PostgreSQL, make sure the database exists before running `init-db`.

### Database Migrations

When you make changes to database models, you'll need to create and apply migrations:

```bash
# Create a migration after changing models
flask db migrate -m "Description of your changes"

# Apply pending migrations
flask db upgrade
```

### Migration Management

Other useful migration commands:

```bash
# Show current migration status
flask db current

# Roll back the last migration
flask db downgrade

# Show migration history
flask db history
```

## Deployment

This section provides instructions for deploying the application to Heroku, a popular cloud platform.

### Deploying to Heroku

#### One-Click Deployment

The easiest way to deploy AI Promoter is with the Heroku Deploy button below. This will create your own instance of the application with all the necessary configuration:

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/snyk-labs/ai-promoter)

**What this does:**
1. Creates a new Heroku application with the required buildpacks
2. Sets up a PostgreSQL database automatically
3. Installs the Heroku Scheduler add-on
4. Prompts you to enter your API keys and configuration
5. Deploys the code and runs initial database setup

**After deployment:**
1. Configure scheduled jobs for content syncing:
   - Open the Scheduler: `heroku addons:open scheduler -a your-app-name`
   - Add jobs for podcasts, blogs, and YouTube as described in the [Scheduler section](#configuring-scheduled-tasks)
2. Set up autonomous social posting if desired (see [Autonomous Posting section](#setting-up-autonomous-social-media-posting))
3. Visit your new application: `heroku open -a your-app-name`

#### Manual Deployment

If you prefer to deploy manually or need more control over the deployment process, follow these steps:

#### Prerequisites

- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) installed
- [Git](https://git-scm.com/) installed
- Heroku account

#### Setup Steps

1. **Login to Heroku**

   ```bash
   heroku login
   ```

2. **Create a new Heroku application**

   ```bash
   heroku create your-app-name
   ```

3. **Add Heroku PostgreSQL add-on**

   ```bash
   heroku addons:create heroku-postgresql:essential-0
   ```

   This will provision a PostgreSQL database and set the `DATABASE_URL` environment variable automatically.

4. **Specify Python version**

   Create a file named `.python-version` in the root directory with the following content:

   ```
   3.12
   ```

   This ensures Heroku uses the latest Python 3.12.x version.

   > **Note:** If you encounter typing-related errors like `AssertionError: Class directly inherits TypingOnly but has additional attributes`, it's a sign of Python version incompatibility. Make sure you're using the `.python-version` file to specify a compatible Python version. It's also crucial that your `Procfile` correctly points to your application factory, e.g., `web: gunicorn "app:create_app()"`.

5. **Set required environment variables**

   ```bash
   # Set a secure random secret key
   heroku config:set SECRET_KEY=$(openssl rand -hex 32)
   
   # Set Gemini API key
   heroku config:set GEMINI_API_KEY=your-gemini-api-key
   
   # Set LinkedIn Integration keys if using this method
   heroku config:set LINKEDIN_CLIENT_ID=your-linkedin-client-id
   heroku config:set LINKEDIN_CLIENT_SECRET=your-linkedin-client-secret
   ```

6. **Create a Procfile**

   Create a file named `Procfile` (no extension) in the root directory with the following content:

   ```
   web: gunicorn "app:create_app()"
   release: FLASK_APP=app.py flask db upgrade
   ```

   This tells Heroku how to run your application:
   - `web`: Specifies the command to start your web server (using Gunicorn)
   - `release`: Specifies commands that run automatically when a new version is deployed (running database migrations)

7. **Add Gunicorn to requirements.txt**

   Ensure `gunicorn` is in your requirements.txt file:

   ```
   gunicorn>=21.2.0
   ```

8. **Deploy to Heroku**

   ```bash
   git add .
   git commit -m "Prepare for Heroku deployment"
   git push heroku main
   ```

9. **Bootstrap the database on Heroku**

   After the first deployment, you need to set up and initialize the database:

   ```bash
   # Run migrations to create all database tables
   heroku run "FLASK_APP=app.py flask db upgrade"
   
   # Initialize the database with required tables and initial data
   heroku run "FLASK_APP=app.py flask init-db"
   ```

   **Troubleshooting SQLAlchemy/typing errors:**

   If you encounter errors like this when running database commands:
   ```
   AssertionError: Class directly inherits TypingOnly but has additional attributes {'__firstlineno__', '__static_attributes__'}
   ```

   This is typically caused by Python version incompatibility. To fix it:

   1. Create or update the `.python-version` file with a compatible Python version:
      ```
      3.12
      ```

   2. Deploy the changes:
      ```bash
      git add .python-version
      git commit -m "Specify Python 3.12 for compatibility"
      git push heroku main
      ```

   3. After deployment completes, try the database commands again.

   **Other database troubleshooting commands:**

   ```bash
   # Check database connection info
   heroku pg:info
   
   # View database credentials
   heroku pg:credentials:url
   
   # Connect to the database directly for troubleshooting
   heroku pg:psql
   ```

   For a fresh start, you can reset the database (⚠️ caution - this deletes all data):

   ```bash
   # Reset the database (removes all data)
   heroku pg:reset DATABASE --confirm your-app-name
   
   # Then run migrations and initialization again
   heroku run "FLASK_APP=app.py flask db upgrade"
   heroku run "FLASK_APP=app.py flask init-db"
   ```

10. **Ensure web dyno is running**

    After deploying, make sure your web dyno is running to serve the application:

    ```bash
    # Check current dynos
    heroku ps

    # If no web dyno is running, start one
    heroku ps:scale web=1

    # To stop the web dyno (e.g., to avoid charges when not in use)
    heroku ps:scale web=0
    ```

    You can also manage dynos through the Heroku Dashboard by:
    - Going to your app's "Resources" tab
    - Under "Dynos", clicking the edit (pencil) icon
    - Moving the slider to enable/disable the web dyno
    - Confirming the change

11. **Set up scheduled content syncing**

    To automate content syncing and social media posting, you'll use the Heroku Scheduler add-on:

    ```bash
    # Install the Heroku Scheduler add-on
    heroku addons:create scheduler:standard
    ```

    Then open the scheduler dashboard to configure your scheduled tasks:

    ```bash
    heroku addons:open scheduler
    ```

    ### <a id="configuring-scheduled-tasks"></a>Configuring Scheduled Tasks

    In the Heroku Scheduler dashboard:

    1. Click on **Create Job**
    2. Set the frequency (e.g., **Every hour** or as defined in your `config.py` Celery beat schedule).
    3. Enter the command to run. For Celery Beat, which manages scheduled tasks defined in `config.py` (like `fetch-content-hourly` and `initiate-posts-friday`), you'll run the Celery beat process.
    4. Click **Save Job**

    ### Example Scheduler Commands on Heroku

    **Run Celery Beat to handle all scheduled tasks (recommended):**
    This command starts the Celery beat scheduler, which will periodically run tasks like `fetch_content_task` and `initiate_posts` based on the `beat_schedule` in your `config.py`.
    ```
    celery -A celery_app beat -s /tmp/celerybeat-schedule --loglevel=INFO
    ```
    *Note: The `-s /tmp/celerybeat-schedule` stores the schedule state in a temporary file, suitable for Heroku's ephemeral filesystem. Ensure your `celery_app` is correctly referenced; it might be `celery_app.celery` or similar depending on your project structure if `celery_app.py` defines `celery = Celery(...)`.*

    **Run specific tasks directly (less common for scheduled, more for ad-hoc or if not using beat):**

    **Trigger content fetching hourly (if not using Celery Beat for this):**
    ```
    FLASK_APP=app.py flask trigger-fetch-content
    ```

    **Trigger autonomous social media posting (if `auto-post` is a Flask CLI command):**
    This example assumes an `auto-post` command exists. The current codebase uses `tasks.notifications.initiate_posts` scheduled via Celery Beat.
    ```
    FLASK_APP=app.py flask auto-post --limit=3 
    ```
    *Review your `config.py` and `cli/` commands for the exact tasks and how they are intended to be run.*


    ### <a id="setting-up-autonomous-social-media-posting"></a>Setting Up Autonomous Social Media Posting

    Autonomous social media posting is typically handled by the `tasks.notifications.initiate_posts` Celery task, which is scheduled to run on Fridays at 9 AM by default via Celery Beat (see `config.py`). Ensure Celery Beat is running on Heroku (as shown above) for this to work automatically.

12. **Open your application**

    ```bash
    heroku open
    ```

### Setting Up Okta SSO with Heroku

#### Creating an Okta Application

1. **Sign in to your Okta Developer Console**

   Go to https://developer.okta.com/ and sign in to your account.

2. **Create a new application**

   - Click on "Applications" in the top menu
   - Click "Create App Integration"
   - Select "OIDC - OpenID Connect" as the sign-in method
   - Select "Web Application" as the application type
   - Click "Next"

3. **Configure the application**

   - Name: Enter a name for your application (e.g., "AI Promoter")
   - Logo (optional): Upload your application logo
   - Sign-in redirect URIs: `https://your-app-name.herokuapp.com/auth/okta/callback`
   - Sign-out redirect URIs: `https://your-app-name.herokuapp.com`
   - Assignments:
     - Select "Allow everyone in your organization to access" for all employees, or
     - Select "Limit access to selected groups" to restrict access

4. **Save the application**

   After saving, Okta will provide you with:
   - Client ID
   - Client Secret
   - Okta Domain
   
   Save these for the next step.

#### Configuring Okta with Heroku

1. **Set Okta environment variables**

   ```bash
   # Enable Okta SSO
   heroku config:set OKTA_ENABLED=true
   
   # Okta application credentials
   heroku config:set OKTA_CLIENT_ID=your-client-id
   heroku config:set OKTA_CLIENT_SECRET=your-client-secret
   
   # Okta domain with authorization server path
   # Format: https://your-okta-domain.okta.com/oauth2/default
   heroku config:set OKTA_ISSUER=https://your-okta-domain.okta.com/oauth2/default
   
   # Redirect URI (must match what you set in Okta)
   heroku config:set OKTA_REDIRECT_URI=https://your-app-name.herokuapp.com/auth/okta/callback
   ```

2. **Deploy the changes**

   ```bash
   git push heroku main
   ```

3. **Test Okta SSO**

   Visit your application and click on the "Sign in with Company SSO" button to test the Okta integration.

#### Troubleshooting Okta SSO

If you encounter issues with Okta SSO:

1. **Check environment variables**

   Ensure all Okta environment variables are set correctly:
   
   ```bash
   heroku config:get OKTA_CLIENT_ID
   heroku config:get OKTA_ISSUER
   heroku config:get OKTA_REDIRECT_URI
   ```

2. **Check Okta application settings**

   - Verify that the redirect URIs match exactly
   - Ensure the application is assigned to the appropriate users or groups
   - Check if the authorization server in the issuer URL is correct

3. **Check Heroku logs**

   ```bash
   heroku logs --tail
   ```

4. **Update callback URL in Okta**

   If your Heroku app URL changes, remember to update the callback URL in your Okta application settings.

## Development

- The main application logic is in `app.py`
- Database models are defined in the `models` package, with each model in its own file
- CLI commands are in `cli.py`
- HTML templates are in the `templates` directory

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Celery Setup

Celery is used for background task processing, such as fetching content, generating social media posts, and sending notifications. The Celery application is initialized within `app.py` using the `celery_init_app` function, and tasks are defined in the `tasks/` package.

The Celery beat scheduler is configured in `config.py` under the `CELERY['beat_schedule']` dictionary. This schedule defines when periodic tasks (like fetching content or initiating posts) should run.

1. Start the Celery worker:
```bash
flask worker --loglevel=info
```
This command is a custom Flask CLI command defined in `app.py` that starts a Celery worker.

2. Start the Celery Beat scheduler (to run scheduled tasks like fetching content):
```bash
celery -A celery_app beat -s ./celerybeat-schedule --loglevel=INFO
```
*Note: Ensure `celery_app` correctly points to your Celery application instance. The `-s ./celerybeat-schedule` flag tells Celery Beat where to store its schedule database.*

3. (Optional) Start Flower for task monitoring:
```bash
celery -A celery_app flower
```

4. Run the Flask application:
```bash
flask run --port 5001
```
*Note: The application runs on port 5001 by default if `if __name__ == "__main__":` block in `app.py` is executed.*

## License

MIT 