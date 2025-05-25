# Refactor report for `legacyfile.py`

Refactored Code:

```python
import sys

def create_user(id, name):
    user = {}
    user["id"] = id
    user["name"] = name
    user["status"] = "inactive" if id % 10 == 0 else "active"
    return user

def print_users(users):
    for user in users:
        print("ID: " + str(user["id"]))
        print("Name: " + user["name"])
        print("Status: " + user["status"])
        print("----")

def main():
    users = [create_user(i, "User" + str(i)) for i in range(50)]
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "print":
            print_users(users)
        else:
            print("Unknown command")

if __name__ == "__main__":
    main()
```

Explanation:
1. Created a `create_user` function to encapsulate the logic of creating a user dictionary.
2. Moved the user creation logic to a list comprehension within the `main` function for better readability.
3. Simplified the `print_users` function to iterate directly over the `users` list and print user details.
4. Removed unnecessary try-except block as there are no specific exceptions to catch.
5. Improved code structure and readability by breaking down the logic into functions.