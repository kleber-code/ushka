from ushka.http import Request

def get(name: str, request: Request):
    user_agent = request.headers.get('user-agent', 'desconhecido')
    return f"Hello, {name}! Welcome, user of {user_agent}."
