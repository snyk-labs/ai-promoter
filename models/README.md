# Models Package

This package contains all database models for the application, organized into separate files for better maintainability.

## Package Structure

- `__init__.py` - Package initialization that imports and exports all models
- `user.py` - User model for authentication and profile data
- `content.py` - Unified Content model for all types of content (articles, videos, podcasts)

## Usage

Models can be imported directly from the package:

```python
from models import User, Content

# Or import specific models
from models.user import User
from models.content import Content
```

## Model Relationships

Currently, the models are independent and don't have direct database relationships.

## Adding New Models

To add a new model:

1. Create a new file in the `models` directory (e.g., `models/new_model.py`)
2. Define your model class in that file
3. Import the model in `__init__.py` and add it to the `__all__` list
4. Run database migrations to create the new table 