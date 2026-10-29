"""
Simple Python file for testing refactor functionality.
Contains obvious code quality issues that need refactoring.
"""


def add(x, y):
    """Sum two numbers."""
    return x + y

def multiply(a, b):
    """Multiply two numbers."""
    return a * b

def say_hello(name):
    """Greet someone."""
    greeting = f"Hello {name}"
    return greeting
def is_valid_age(age):
    """Check if age is valid."""
    if age < 0 or age > 150:
        return False
    else:
        return True

def check_valid_age_for_operation(age, operation):
    """Check if the provided age is valid for a given operation."""
    if not is_valid_age(age):
        raise ValueError("Invalid age provided.")
    # ... other functions using `check_valid_age_for_operation`
def double_list_items(items):
    """Process a list of items by doubling each item."""
    result = []
    for item in items:
        item *= 2
        result.append(item)
    return result
