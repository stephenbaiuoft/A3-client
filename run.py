#!venv/bin/python
from app import webapp
# run local ONLY to avoid potential incoming traffic on my own machine

webapp.run(host='localhost',port=5001, debug=True)
#webapp.run(host='0.0.0.0')
