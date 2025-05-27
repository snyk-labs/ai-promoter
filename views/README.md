# Views Package

This package contains the view functions (route handlers) for the application, organized into blueprints.

## Structure

- `__init__.py`: Makes the directory a Python package
- `main.py`: Contains the main routes for the application (e.g., the home page)
- `api.py`: Contains the API routes for the application (e.g., promotion endpoints)
- `auth.py`: Contains the standard authentication routes (login, logout, registration, etc.)
- `okta_auth.py`: Contains the Okta SSO authentication routes

## Adding New Views

To add a new view:

1. If it fits into an existing category, add it to the appropriate blueprint file
2. If it's a new category, create a new blueprint file and register it in `app.py`

## View Structure

Each view follows this general pattern:

```python
@bp.route('/path', methods=['GET'])
def view_name():
    # Logic to prepare data
    return render_template('template.html', data=data)
```

For API views:

```python
@bp.route('/api/path', methods=['POST'])
@login_required  # If authentication is required
def api_view_name():
    # Logic to handle request
    return jsonify({
        'success': True,
        'data': data
    })
```

## Authentication Routes

The authentication system is split into two parts:

### Standard Authentication (`auth.py`)

- `/auth/register`: Register new users
- `/auth/login`: Log in existing users
- `/auth/logout`: Log out users
- `/auth/profile`: View and edit user profiles
- `/auth/linkedin/*`: LinkedIn integration endpoints
- `/auth/x/*`: X/Twitter integration endpoints

### Okta SSO Authentication (`okta_auth.py`)

- `/auth/okta/login`: Start the Okta SSO flow
- `/auth/okta/callback`: Handle the callback from Okta 