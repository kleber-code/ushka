from ushka import Ushka

app = Ushka()


# example of non-autodiscover route for flask lovers
@app.get("/high")
def high_route():
    return "VERY HIGH"


if __name__ == "__main__":
    app.run()
