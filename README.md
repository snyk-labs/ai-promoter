# AI Promoter

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

- **Models**: Defined in the `models` package, each in its own file, representing the data structure
- **Views**: Located in the `views/` package, containing:
  - `main.py`: Main page routes
  - `api.py`: API endpoints for promotion
  - `auth.py`: Standard authentication routes
  - `okta_auth.py`: Okta SSO authentication routes
- **Templates**: Stored in the `templates/` directory

The application is structured as follows:

- `app.py`: Application factory and configuration
- `extensions.py`: Flask extensions initialization
- `models/`: Database models organized by entity
  - `__init__.py`: Imports and exports all models
  - `user.py`: User model
  - `episode.py`: Podcast episode model
  - `post.py`: Blog post model
  - `video.py`: YouTube video model
- `cli/`: Command-line interface commands
- `helpers/`: Utility functions and modules
- `migrations/`: Database migration files
- `views/`: View functions organized by feature

## Prerequisites

- Python 3.12 (there are issues with Python 3.13 currently due to the aiohttp library)
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
python -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
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

## Configuration

Before running the application, you need to set up the following environment variables:

### Required Environment Variables

```bash
# Flask secret key (for session security)
export SECRET_KEY="your-secure-random-key"  # On Windows: set SECRET_KEY="your-secure-random-key"

# OpenAI API key (required for generating social media content)
export OPENAI_API_KEY="your-openai-api-key"  # On Windows: set OPENAI_API_KEY="your-openai-api-key"

# Arcade API key (required for social media posting)
export ARCADE_API_KEY="your-arcade-api-key"  # On Windows: set ARCADE_API_KEY="your-arcade-api-key"
```

You can generate a secure random key for SECRET_KEY using:

```bash
# On macOS/Linux
openssl rand -hex 32

# On Windows (in PowerShell)
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

### Optional Environment Variables

```bash
# Database configuration (defaults to SQLite)
export DATABASE_URL="sqlite:///ai-promoter.db"  # Change if using PostgreSQL or other database

# Enable/disable Okta SSO (defaults to false)
export OKTA_ENABLED="false"  # Set to "true" to enable Okta SSO

# Company configuration
export COMPANY_NAME="Your Company Name"  # Displayed in the UI and page titles
export UTM_PARAMS="?utm_source=yourcompany.com&utm_medium=social"  # UTM parameters to append to all promoted URLs
export DASHBOARD_BANNER="<p>Custom HTML banner for non-admin users</p>"  # HTML content to display at the top of the dashboard
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

The application includes CLI commands to sync content from RSS feeds. You can run these manually or set them up as scheduled tasks.

#### Syncing Podcast Episodes

To sync podcast episodes manually:

```bash
# First, ensure you're in your virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Set the Flask application
export FLASK_APP=app.py  # On Windows: set FLASK_APP=app.py

# Run the sync command with your podcast's RSS feed URL
flask sync-podcast "YOUR_PODCAST_RSS_URL"

# For example, for The Secure Developer podcast:
flask sync-podcast "https://feeds.simplecast.com/47yfLpm0"
```

#### Syncing Blog Posts

To sync blog posts manually:

```bash
# First, ensure you're in your virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Set the Flask application
export FLASK_APP=app.py  # On Windows: set FLASK_APP=app.py

# Run the sync command with your blog's RSS feed URL
flask sync-blog "YOUR_BLOG_RSS_URL"

# For example, for the Snyk blog:
flask sync-blog "https://snyk.io/blog/feed/"
```

#### Syncing YouTube Videos

To sync YouTube videos manually:

```bash
# First, ensure you're in your virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Set the Flask application
export FLASK_APP=app.py  # On Windows: set FLASK_APP=app.py

# Run the sync command with your YouTube channel's RSS feed URL
flask sync-youtube "YOUR_YOUTUBE_CHANNEL_RSS_URL"

# For example:
flask sync-youtube "https://www.youtube.com/feeds/videos.xml?channel_id=UCh4dJzctb0NhSibjU-e2P6w"
```

### Automating Content Updates

To automatically sync new episodes, you can set up a cron job (on Unix-based systems) or a scheduled task (on Windows).

#### Unix/Linux Cron Job

1. Create a shell script named `sync_episodes.sh`:
```bash
#!/bin/bash
cd /path/to/your/ai-promoter
source venv/bin/activate
export FLASK_APP=app.py
flask sync-podcast "YOUR_PODCAST_RSS_URL"
```

2. Make it executable:
```bash
chmod +x sync_episodes.sh
```

3. Add to crontab (runs every hour):
```bash
0 * * * * /path/to/your/sync_episodes.sh
```

#### Windows Scheduled Task

1. Create a batch file named `sync_episodes.bat`:
```batch
cd C:\path\to\your\ai-promoter
call venv\Scripts\activate
set FLASK_APP=app.py
flask sync-podcast "YOUR_PODCAST_RSS_URL"
```

2. Use Windows Task Scheduler to run this batch file on your desired schedule.

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

   Create a file named `runtime.txt` in the root directory with the following content:

   ```
   python-3.11.9
   ```

   This ensures Heroku uses Python 3.11.9 instead of the latest version (3.13+), which may have compatibility issues with SQLAlchemy and Flask-Migrate.

   > **Note:** If you encounter typing-related errors like `AssertionError: Class directly inherits TypingOnly but has additional attributes`, it's a sign of Python version incompatibility. Make sure you're using the `runtime.txt` file to specify a compatible Python version.

5. **Set required environment variables**

   ```bash
   # Set a secure random secret key
   heroku config:set SECRET_KEY=$(openssl rand -hex 32)
   
   # Set OpenAI API key
   heroku config:set OPENAI_API_KEY=your-openai-api-key
   
   # Set Arcade API key if using social media posting
   heroku config:set ARCADE_API_KEY=your-arcade-api-key
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

   1. Create or update the `runtime.txt` file with a compatible Python version:
      ```
      python-3.11.9
      ```

   2. Deploy the changes:
      ```bash
      git add runtime.txt
      git commit -m "Specify Python 3.11.9 for compatibility"
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
    2. Set the frequency (recommended: **Every hour** for content syncing)
    3. Enter the command to run (see examples below)
    4. Click **Save Job**
    
    Repeat this process for each type of content you want to sync.

    ### Example Scheduler Commands

    **Sync podcast episodes hourly:**
    ```
    FLASK_APP=app.py flask sync-podcast "https://feeds.simplecast.com/47yfLpm0"
    ```

    **Sync blog posts hourly:**
    ```
    FLASK_APP=app.py flask sync-blog "https://snyk.io/blog/feed/"
    ```

    **Sync YouTube videos hourly:**
    ```
    FLASK_APP=app.py flask sync-youtube "https://www.youtube.com/feeds/videos.xml?channel_id=UCh4dJzctb0NhSibjU-e2P6w"
    ```

    ### <a id="setting-up-autonomous-social-media-posting"></a>Setting Up Autonomous Social Media Posting

    To enable autonomous social media posting for newly discovered content, add this scheduled job:

    1. In the Scheduler dashboard, click **Create Job**
    2. Set frequency to **Every hour** (runs 30 minutes after content syncing)
    3. Enter this command:
       ```
       FLASK_APP=app.py flask auto-post --limit=3
       ```
       The `--limit` parameter controls the maximum number of posts to create per run

    ### Best Practices for Scheduling

    - **Stagger your jobs**: Schedule content syncing to run at the top of the hour and auto-posting to run 30 minutes later
    - **Monitor usage**: Check your application logs to ensure tasks are completing successfully
    - **Adjust frequency**: For high-volume feeds, consider more frequent syncing (every 10 minutes)
    - **Check logs**: If a job fails, view logs with `heroku logs --ps scheduler`

    ### Viewing Scheduler Logs

    To check if your scheduled jobs are running properly:

    ```bash
    # View recent scheduler logs
    heroku logs --ps scheduler

    # View all application logs
    heroku logs --tail
    ```

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

1. Start the Celery worker:
```bash
celery -A celery_app worker --loglevel=info
```

2. (Optional) Start Flower for task monitoring:
```bash
celery -A celery_app flower
```

3. Run the application:
```bash
flask run
```

## License

MIT 