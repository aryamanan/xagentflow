from sqlalchemy.orm import DeclarativeBase

# Define the single Base for all models
class Base(DeclarativeBase):
    pass

# Import all models here so they are registered with SQLAlchemy
# from app.models.task import Task # REMOVE THIS IMPORT

__all__ = ["Base"] # Removed Task from __all__ 