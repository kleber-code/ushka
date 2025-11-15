from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    print("Try visiting the following URLs:")
    print("  - http://127.0.0.1:8000/")
    print("  - http://127.0.0.1:8000/hello")
    print("  - http://127.0.0.1:8000/hello/Developer")
    app.run("127.0.0.1", 8000)
