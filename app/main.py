from flask import render_template, redirect, url_for, request, g, session
from app import webapp
import random
import hashlib
import mysql.connector
from app.config import db_config
from app.config import bucket_name
import os
from wand.image import Image
import boto3
from app import config

# webapp.secret_key = os.urandom(24)



@webapp.route('/',methods=['GET'])
@webapp.route('/index',methods=['GET'])
def main():
    """
    Display the welcome page where you could login or sign up.
    """
    return render_template("main.html",title="Photos Browser")


def connect_to_database():
    return mysql.connector.connect(user=db_config['user'],
                                   password=db_config['password'],
                                   host=db_config['host'],
                                   database=db_config['database'])


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_to_database()
    return db


@webapp.teardown_appcontext
def teardown_db(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@webapp.route('/index/login', methods=['POST'])
def user_login():
    username = request.form.get('usrn',"")
    pwd = request.form.get('pwd',"")

    #check if the account exists
    cnx = get_db()
    cursor = cnx.cursor(buffered=True)
    query = '''SELECT hashed_pwd, salt FROM users WHERE username = %s'''
    cursor.execute(query,(username,))
    row = cursor.fetchone()

    error = False
    if row is None:
        error=True
        error_msg = "Error: Username doesn't exist!"
    if error:
        return render_template("main.html",title="Photo Browser", login_error_msg=error_msg, log_username=username)

    # if username exists, is pwd correct?
    salt = row[1]
    hashed_pwd = row[0]
    pwd += salt
    if hashed_pwd == hashlib.sha256(pwd.encode()).hexdigest():
        # add to the session
        session['authenticated'] = True
        session['username'] = username
        return redirect(url_for('home_page', username=username))
    else:
        error=True
        error_msg = "Error: Wrong password or username! Please try again!"
    if error:
        return render_template("main.html",title="Photo Browser", login_error_msg=error_msg, log_username=username)


@webapp.route('/index/register', methods=['POST'])
def user_signup():
    username = request.form.get('newusrn')
    pwd = request.form.get('newpwd')

    # check length of input
    error = False
    if len(username)<6 or len(username)>20 or len(pwd)<6 or len(pwd)>20:
        error=True
        error_msg = "Error: Both username and password should have length of 6 to 20!"
    if error:
        return render_template("main.html",title="Photo Browser", signup_error_msg=error_msg, sign_username=username)

    cnx = get_db()
    cursor = cnx.cursor(buffered=True)

    # check whether username exists
    query = '''SELECT * FROM users WHERE username = %s'''
    cursor.execute(query,(username,))
    row = cursor.fetchone()
    error = False
    if row is not None:
        error=True
        error_msg = "Error: Username already exists!"
    if error:
        return render_template("main.html", title="Photo Browser", signup_error_msg=error_msg, sign_username=username)

    # create a salt value
    ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    chars=[]
    for i in range(8):
        chars.append(random.choice(ALPHABET))
    salt = "".join(chars)
    pwd += salt
    hashed_pwd = hashlib.sha256(pwd.encode()).hexdigest()

    query = '''INSERT INTO users (user_id, username, hashed_pwd, salt)
    VALUES (NULL, %s, %s, %s)'''
    cursor.execute(query, (username, hashed_pwd, salt))
    cnx.commit()
    # add to the session
    session['authenticated'] = True
    session['username'] = username
    return redirect(url_for('home_page', username=username))


@webapp.route('/home/<username>', methods=['GET'])
def home_page(username):
    """
    Display a list of thumbnails of pre-uploaded pictures of the authenticated user.
    :param username: the username of the authenticated user.
    """
    # make sure the user is the one logging in the session
    if 'authenticated' not in session:
        return redirect(url_for('main'))
    if session.get('username', '') != username:
        return redirect(url_for('home_page', username=session['username']))

    cnx = get_db()
    cursor = cnx.cursor(buffered=True)
    # fpath = './app/static/photos/{}'.format(username)
    # if not os.path.exists(fpath):
    #     os.makedirs(fpath)
    query = '''SELECT images.img_id, images.img_name, images.filename FROM images, 
    users WHERE users.username = %s AND images.owned_by = users.user_id'''
    cursor.execute(query, (username,))  # current login user

    thumbnail_row_set = get_thumb_crow_set(username, cursor)


    return render_template("home.html", title="Your photos", cursor=cursor, username=username, set=thumbnail_row_set)


# put everything jinja needs in this array, and jinja2 will use this set instead
def get_thumb_crow_set(username, cursor):
    thumbnail_row_set = []
    client = boto3.client('s3')
    for i in range(cursor.rowcount):
        row = cursor.fetchone()
        img_id = row[0]
        filename = row[2]

        file_key = username + "/thumbnail_" + filename
        params = {
            'Bucket': config.bucket_name,
            'Key': file_key
        }
        url = client.generate_presigned_url('get_object',
                                        params,
                                        ExpiresIn=3600
                                        )
        print("url thumbnail is: ", url)
        thumbnail_row_set.append([img_id,url, filename])

    for s in thumbnail_row_set:
        print("printing thumbnail-row-set")
        print(s[1])
    # for debugging
    return thumbnail_row_set


@webapp.route('/home/<username>/logout', methods=['GET'])
def logout(username):
    # session.pop('username', None)
    session.clear()
    return redirect(url_for('main'))


@webapp.route('/home/<username>/<int:img_id>', methods=['GET'])
def image_display(username, img_id):
    """
    Display the picture's information, the original picture and its tranformations
    after clicking on the thumbnail on home page.
    :param username: the username of the authenticated user.
    :param img_id: the image id of the image corresponding to the thumbnail the user clicked on.
    """

    # make sure the user is the one logging in the session
    if 'authenticated' not in session:
        return redirect(url_for('main'))
    if session.get('username', '') != username:
        return redirect(url_for('home_page', username=session['username']))

    cnx = get_db()
    cursor = cnx.cursor(buffered=True)
    query = "SELECT img_name, location, description, owned_by, filename FROM images WHERE img_id = %s"
    cursor.execute(query,(img_id,))
    row = cursor.fetchone()
    name = row[0]
    location = row[1]
    desc = row[2]
    owner = row[3]
    filename = row[4]
    # make sure the user unable to see others' photos via entering URL
    query = "SELECT username FROM users WHERE user_id = %s"
    cursor.execute(query,(owner,))
    if cursor.fetchone()[0] != username:
        return redirect(url_for('home_page', username=session['username']))

    # get s3 url
    img_src_set = get_s3_object_url_set(username, filename)
    return render_template("image_display.html", title="Photo display",img_id=img_id,
                           img_name=name, location=location, description = desc, filename=filename, username=username,
                           img_src_set=img_src_set
                           )


# return array of image urls [] for username
def get_s3_object_url_set(username, filename):
    s3 = boto3.resource('s3')
    # bucket = s3.Bucket(config.bucket_name)
    client = boto3.client('s3')

    file_url_set = []
    file_extension = ["/", "/scaleup_", "/scaledown_", "/grayscale_"]
    Params={
        'Bucket': config.bucket_name,
        'Key': None
    }

    for ext in file_extension:
        file_key = username + ext + filename
        Params['Key'] = file_key
        url = client.generate_presigned_url('get_object',
                                            Params,
                                            ExpiresIn=3600
                                            )
        # for debugging
        print(url)
        file_url_set.append(url)

    return file_url_set



@webapp.route('/home/<username>/upload', methods=['GET'])
def file_upload(username):
    # make sure the user is the one logging in the session
    if 'authenticated' not in session:
        return redirect(url_for('main'))
    if session.get('username', '') != username:
        return redirect(url_for('home_page', username=session['username']))
    return render_template("file_upload.html", title="Upload your photo", username=username)


@webapp.route('/home/<username>/upload', methods=['POST'])
def file_uploaded(username):
    """
    Process the information the user entered and the file uploaded from the file upload page.
    :param username: the username of the authenticated user.
    """
    # make sure the user is the one logging in the session
    if 'authenticated' not in session:
        return redirect(url_for('main'))
    if session.get('username', '') != username:
        return redirect(url_for('home_page', username=session['username']))

    # where to store the image
    # fpath = './app/static/photos/{}'.format(username)
    fpath = './app/static'
    allowed_ext = set(['jpg','jpeg','png','gif'])
    f = request.files['myFile']
    fn = f.filename
    # handling filename length
    if len(fn) > 30:
        try:
            rez = fn.rsplit('.', 1)
            fn = rez[0][0:26] + "." + rez[1]
            print("fn formatted is: " + fn)
        except:
            # invalid file input
            return redirect(url_for('home_page', username=session['username']))

    img_name = request.form.get('img_name',"")
    if img_name == "":
        img_name = fn
    if len(img_name)>20:
        img_name = img_name[:20]
    location = request.form.get('location',"")
    description = request.form.get('description',"")

    # connect to s3
    s3 = boto3.resource('s3')
    # get my own bucket name
    bucket = s3.Bucket(bucket_name)

    if '.' in fn and fn.rsplit('.',1)[1].lower() in allowed_ext:
        # save to local storage first
        f.save(os.path.join(fpath, fn))
        # save the original picture to s3
        original = open(os.path.join(fpath, fn), 'rb')
        bucket.upload_fileobj(original, username+'/'+fn)
        # bucket.put_object(Key=username+'/'+fn, Body=original)
        original.close()

        with Image(filename=os.path.join(fpath, fn)) as img:
            size = img.size
            with img.convert('jpg') as converted1:
                # create thumbnail
                if size[0] < size[1]:
                    converted1.crop(0, (size[1] - size[0]) // 2, width=size[0], height=size[0])
                else:
                    converted1.crop((size[0] - size[1]) // 2, 0, width=size[1], height=size[1])
                converted1.sample(150, 150)
                # save to local, read, save to s3, delete it from local
                converted1.save(filename=os.path.join(fpath, 'thumbnail_'+fn))
                thumb = open(os.path.join(fpath, 'thumbnail_'+fn), 'rb')
                bucket.upload_fileobj(thumb, username + '/thumbnail_' + fn)
                thumb.close()

            with img.convert('jpg') as converted2:
                # scale up
                converted2.resize(int(size[0]*1.2), int(size[1]*1.2))
                # converted2.save(filename=os.path.join(fpath, "scaleup_"+fn))
                # save the scaled-up to s3
                converted2.save(filename=os.path.join(fpath, 'scaleup_' + fn))
                scaleup = open(os.path.join(fpath, 'scaleup_' + fn), 'rb')
                bucket.upload_fileobj(scaleup, username + '/scaleup_' + fn)
                scaleup.close()

            with img.convert('jpg') as converted3:
                # scale down
                converted3.resize(int(size[0] * 0.8), int(size[1] * 0.8))
                # converted3.save(filename=os.path.join(fpath, "scaledown_" + fn))
                # save the scaled down to s3
                converted3.save(filename=os.path.join(fpath, 'scaledown_' + fn))
                scaledown = open(os.path.join(fpath, 'scaledown_' + fn), 'rb')
                bucket.upload_fileobj(scaledown, username + '/scaledown_' + fn)
                scaledown.close()

            with img.convert('jpg') as converted4:
                # grayscale
                converted4.type = 'grayscale'
                # converted4.save(filename=os.path.join(fpath, "grayscale_" + fn))
                # save the grayscale to s3
                converted4.save(filename=os.path.join(fpath, 'grayscale_' + fn))
                grayscale = open(os.path.join(fpath, 'grayscale_' + fn), 'rb')
                bucket.upload_fileobj(grayscale, username + '/grayscale_' + fn)
                grayscale.close()

        # delete the original image from local storage
        os.remove(os.path.join(fpath, 'thumbnail_' + fn))
        os.remove(os.path.join(fpath, 'scaleup_' + fn))
        os.remove(os.path.join(fpath, 'scaledown_' + fn))
        os.remove(os.path.join(fpath, 'grayscale_' + fn))
        os.remove(os.path.join(fpath, fn))

        # object_acl = s3.ObjectAcl('cloud-computing-photo-storage', username+'/*')
        # response = object_acl.put(ACL='public-read')
        bucket.Acl().put(ACL='public-read')

        cnx = get_db()
        cursor = cnx.cursor(buffered=True)
        query = '''SELECT user_id FROM users WHERE username = %s'''
        cursor.execute(query,(username,))
        user_id = cursor.fetchone()[0]
        query = '''INSERT INTO images (img_id, img_name, location, description, owned_by, filename)
        VALUES (NULL, %s, %s, %s, %s, %s)'''
        cursor.execute(query,(img_name, location, description, user_id, fn))
        cnx.commit()
        return redirect(url_for('home_page',username=username))
    else:
        error = True
        error_msg = "Error: Invalid photo format! Please choose from jpg, jpeg, gif, png!"
        if error:
            return render_template("file_upload.html", title="Upload your photo", username=username, error_message=error_msg)


@webapp.route('/test/FileUpload', methods=['GET','POST'])
def test_file_upload():
    """
    A test page for file upload where you could login with valid username and password and upload a picture at the same time.
    """
    if request.method == 'GET':
        return render_template("for_test.html", title="File Upload Test")

    if request.method == 'POST':
        username = request.form.get('userID', "")
        pwd = request.form.get('password', "")

        # check if the account exists
        cnx = get_db()
        cursor = cnx.cursor(buffered=True)
        query = '''SELECT hashed_pwd, salt FROM users WHERE username = %s'''
        cursor.execute(query, (username,))
        row = cursor.fetchone()

        error = False
        if row is None:
            error = True
            error_msg = "Error: Username doesn't exist!"
        if error:
            return render_template("for_test.html", title="File Upload Test", login_error_msg=error_msg, log_username=username)

        # if username exists, is pwd correct?
        salt = row[1]
        hashed_pwd = row[0]
        pwd += salt
        if hashed_pwd == hashlib.sha256(pwd.encode()).hexdigest():
            # add to the session
            session['authenticated'] = True
            session['username'] = username
            fpath = './app/static'
            allowed_ext = set(['jpg', 'jpeg', 'png', 'gif'])
            f = request.files['uploadedfile']
            fn = f.filename

            # handling filename length
            if len(fn) > 30:
                try:
                    rez = fn.rsplit('.', 1)
                    fn = rez[0][0:26] + "." + rez[1]
                    # print("fn formatted is: " + fn)
                except:
                    # invalid file input
                    return redirect(url_for('home_page', username=session['username']))

            img_name = fn
            # if img_name == "":
            #     img_name = fn
            if len(img_name) > 20:
                img_name = img_name[:20]
            location = ""
            description = ""

            # connect to s3
            s3 = boto3.resource('s3')
            bucket = s3.Bucket('cloud-computing-photo-storage')

            if '.' in fn and fn.rsplit('.', 1)[1].lower() in allowed_ext:
                # save to local storage first
                f.save(os.path.join(fpath, fn))
                # save the original picture to s3
                original = open(os.path.join(fpath, fn), 'rb')
                bucket.upload_fileobj(original, username + '/' + fn)
                # bucket.put_object(Key=username+'/'+fn, Body=original)
                original.close()

                with Image(filename=os.path.join(fpath, fn)) as img:
                    size = img.size
                    with img.convert('jpg') as converted1:
                        # create thumbnail
                        if size[0] < size[1]:
                            converted1.crop(0, (size[1] - size[0]) // 2, width=size[0], height=size[0])
                        else:
                            converted1.crop((size[0] - size[1]) // 2, 0, width=size[1], height=size[1])
                        converted1.sample(150, 150)
                        # save to local, read, save to s3, delete it from local
                        converted1.save(filename=os.path.join(fpath, 'thumbnail_' + fn))
                        thumb = open(os.path.join(fpath, 'thumbnail_' + fn), 'rb')
                        bucket.upload_fileobj(thumb, username + '/thumbnail_' + fn)
                        thumb.close()

                    with img.convert('jpg') as converted2:
                        # scale up
                        converted2.resize(int(size[0] * 1.2), int(size[1] * 1.2))
                        # converted2.save(filename=os.path.join(fpath, "scaleup_"+fn))
                        # save the scaled-up to s3
                        converted2.save(filename=os.path.join(fpath, 'scaleup_' + fn))
                        scaleup = open(os.path.join(fpath, 'scaleup_' + fn), 'rb')
                        bucket.upload_fileobj(scaleup, username + '/scaleup_' + fn)
                        scaleup.close()

                    with img.convert('jpg') as converted3:
                        # scale down
                        converted3.resize(int(size[0] * 0.8), int(size[1] * 0.8))
                        # converted3.save(filename=os.path.join(fpath, "scaledown_" + fn))
                        # save the scaled down to s3
                        converted3.save(filename=os.path.join(fpath, 'scaledown_' + fn))
                        scaledown = open(os.path.join(fpath, 'scaledown_' + fn), 'rb')
                        bucket.upload_fileobj(scaledown, username + '/scaledown_' + fn)
                        scaledown.close()

                    with img.convert('jpg') as converted4:
                        # grayscale
                        converted4.type = 'grayscale'
                        # converted4.save(filename=os.path.join(fpath, "grayscale_" + fn))
                        # save the grayscale to s3
                        converted4.save(filename=os.path.join(fpath, 'grayscale_' + fn))
                        grayscale = open(os.path.join(fpath, 'grayscale_' + fn), 'rb')
                        bucket.upload_fileobj(grayscale, username + '/grayscale_' + fn)
                        grayscale.close()

                # delete the original image from local storage
                os.remove(os.path.join(fpath, 'thumbnail_' + fn))
                os.remove(os.path.join(fpath, 'scaleup_' + fn))
                os.remove(os.path.join(fpath, 'scaledown_' + fn))
                os.remove(os.path.join(fpath, 'grayscale_' + fn))
                os.remove(os.path.join(fpath, fn))

                bucket.Acl().put(ACL='public-read')

                cnx = get_db()
                cursor = cnx.cursor(buffered=True)
                query = '''SELECT user_id FROM users WHERE username = %s'''
                cursor.execute(query, (username,))
                user_id = cursor.fetchone()[0]
                query = '''INSERT INTO images (img_id, img_name, location, description, owned_by, filename)
                VALUES (NULL, %s, %s, %s, %s, %s)'''
                cursor.execute(query, (img_name, location, description, user_id, fn))
                cnx.commit()
                return redirect(url_for('home_page', username=username))
            else:
                error = True
                error_msg = "Error: Invalid photo format! Please choose from jpg, jpeg, gif, png!"
                if error:
                    return render_template("file_upload.html", title="Upload your photo", username=username,
                                           error_message=error_msg)
        else:
            error = True
            error_msg = "Error: Wrong password or username! Please try again!"
        if error:
            return render_template("for_test.html", title="File Upload Test", login_error_msg=error_msg, log_username=username)
