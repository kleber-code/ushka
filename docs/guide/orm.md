# ORM (Object-Relational Mapper)

Interacting with a database can sometimes feel like trying to speak a different language. You have to write SQL queries, manage connections, and handle a lot of boilerplate code.

An Object-Relational Mapper, or ORM, is like a universal translator. It lets you interact with your database using the Python objects and methods you already know and love.

Ushka's ORM is built on the powerful SQLAlchemy library, but it provides a simple, Active Record-style interface. This means that your database models are not just definitions; they are active objects that know how to save, delete, and query themselves.

## Defining a Model

Think of a model as a blueprint for a table in your database. You define your models by creating a class that inherits from `db.Model`.

Let's create a simple `User` model:

```python
from ushka.features.orm import db

class User(db.Model):
    __tablename__ = "users"  # The name of the table in the database

    id = db.BigInt(primary_key=True)
    name = db.String(length=100)
    email = db.String(unique=True)
    is_active = db.Bool(default=True)

    def __repr__(self):
        return f"<User {self.id}: {self.name}>"
```

In this example, we're defining a `users` table with four columns: `id`, `name`, `email`, and `is_active`. We use the helper methods on the `db` object (`db.String`, `db.Bool`, etc.) to define the column types.

> **Ushka Tip:** Using `__repr__` is like giving your models a name tag. It's a small thing, but it makes debugging much more pleasant when you see `<User 1: Alice>` instead of a generic object address.

## CRUD Operations: The Bread and Butter

CRUD stands for Create, Read, Update, and Delete. These are the fundamental operations you'll perform on your data. With Ushka's ORM, these operations are simple and intuitive.

### Create

To create a new record in the database, you can create an instance of your model and call the `save()` method, or use the `create()` class method as a convenient shortcut.

```python
# The create() shortcut (recommended)
user = await User.create(name="Alice", email="alice@example.com")

# The longer way
new_user = User(name="Bob", email="bob@example.com")
await new_user.save()
```

### Read

There are several ways to read data from the database.

```python
# Get all users
users = await User.all()

# Get a single user by their primary key
user = await User.get(1)

# Get the first user who matches a condition
user = await User.first(name="Alice")

# Get a list of users who match a condition
active_users = await User.filter(is_active=True)
```

### Update

To update a record, you simply change the attributes of a model instance and then call `save()`.

```python
user = await User.first(name="Alice")
if user:
    user.name = "Alicia"
    await user.save()
```

### Delete

To delete a record, call the `delete()` method on a model instance.

```python
user = await User.first(name="Bob")
if user:
    await user.delete()
```

## Asynchronous All the Way

Notice the `await` keyword in all the examples above? That's because Ushka's ORM is fully asynchronous. This is a crucial feature for a modern web framework, as it means your application can handle other tasks while it's waiting for the database to respond. This leads to better performance and scalability.

By providing a simple yet powerful interface on top of SQLAlchemy's async capabilities, Ushka's ORM makes database interactions a seamless and enjoyable part of your development process.
