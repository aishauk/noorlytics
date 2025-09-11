 To incrementally refactor the given `legacyfile.py`, I propose the following safe refactoring steps:

1. **Extract a function for user status determination**
   - Create a new function `get_user_status(id)` to determine the user's status based on the id.
   - Replace the status assignment in `create_user(id, name)` with a call to this new function.

```diff
- def create_user(id, name):
+ def create_user(id, name):
       user = {}
       user["id"] = id
       user["name"] = name
       user["status"] = get_user_status(id)
       return user

-    user["status"] = "inactive" if id % 10 == 0 else "active"
+   def get_user_status(id):
+       return "inactive" if id % 10 == 0 else "active"
```

2. **Introduce a User class**
   - Create a `User` class to encapsulate user data and behavior.
   - Replace the dictionary-based representation of users with instances of the new `User` class.

```diff
- def create_user(id, name):
+ class User:
+    def __init__(self, id, name, status):
+        self.id = id
+        self.name = name
+        self.status = status

-    user = {}
-    user["id"] = id
-    user["name"] = name
-    user["status"] = get_user_status(id)
-    return user

- def print_users(users):
+ def print_users(users):
+    for user in users:
+        print("ID: " + str(user.id))
+        print("Name: " + user.name)
+        print("Status: " + user.status)
+        print("----")
```

3. **Modify the main function to create User instances**
   - Replace the list comprehension in `main()` with a loop that creates and initializes each user as an instance of the new `User` class.

```diff
- users = [create_user(i, "User" + str(i)) for i in range(50)]
+ users = []
+ for i in range(50):
+     users.append(User(i, "User" + str(i), get_user_status(i)))
```

4. **Update the command-line argument handling**
   - Modify the `if len(sys.argv) > 1:` block to accept a command and perform the appropriate action (printing users or displaying an error message).

```diff
- if len(sys.argv) > 1:
+ if len(sys.argv) > 1 and sys.argv[1] in ["print", "help"]:
        if sys.argv[1] == "print":
            print_users(users)
        elif sys.argv[1] == "help":
            print("Available commands: print, help")
        else:
            print("Unknown command")
```

5. **Add a help message**
   - Add a help message when the user runs the script with the `help` command.

```diff
- elif sys.argv[1] == "help":
+    if len(sys.argv) > 1 and sys.argv[1] == "help":
+        print("This script creates users and prints them to the console.")
+        print("Available commands:")
+        print("- print: Prints all users.")
+        print("- help: Displays this help message.")
```