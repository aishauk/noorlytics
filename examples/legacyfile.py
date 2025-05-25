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