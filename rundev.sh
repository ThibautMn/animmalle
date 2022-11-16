. venv/bin/activate

export FLASK_ENV=development
export FLASK_APP=server.py

flask run -h 0.0.0.0 -p 4800
