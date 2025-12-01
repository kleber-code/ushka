from ushka import Ushka
from ushka.features.template import render

app = Ushka()


# example of non-autodiscover route for flask lovers
@app.get("/high")
def high_route():
    return render("startup.html", {})


if __name__ == "__main__":
    app.run()
