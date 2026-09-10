"""Local development entrypoint.

Real configuration lives in server/app.py; this file exists so that
`python app.py` still starts the server, and so .claude/launch.json has a
stable target. Vercel imports the factory directly instead.
"""

from server.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
