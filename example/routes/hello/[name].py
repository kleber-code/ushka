from ushka.features.template import render


def get(name: str):
    return render("templated_hello.html", {"name": name})
