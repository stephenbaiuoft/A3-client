from flask import Flask

webapp = Flask(__name__)

from app import main
from app import config

webapp.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?faweaewfahg435656245RT'