echo "script invoked" > /home/ubuntu/Desktop/crontab.txt
cd /home/ubuntu/Desktop/A2_web_development
echo current dir is $(pwd) >> /home/ubuntu/Desktop/crontab.txt
sudo ./venv/bin/gunicorn --bind 0.0.0.0:80 --workers=8 --worker-class gevent --access-logfile access.log --error-logfile error.log app:webapp
echo finished invoking gunicorn cmd >> /home/ubuntu/Desktop/crontab.txt