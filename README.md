# convert T.League schedule to ical format

- python -m venv .
- . ./bin/activate
- pip install -r requirements.txt
- python tlg2018.py
  - or: gunicorn tlg2018:app
  - or: FLASK_APP=tlg2018.py flask run

## access

- http://localhost:8080/
