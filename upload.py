from flask import Flask, escape, request, render_template
import pathlib
import boto3
import os
import tempfile
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from pprint import pprint
from datetime import datetime
from werkzeug.utils import secure_filename
from photos import image_sizes, upload_s3, image_info
from PIL import Image

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
images_bucket = os.environ['IMAGES_BUCKET']
albums_table = os.environ['ALBUMS_TABLE']
app = Flask(__name__)

@app.route('/', methods =['GET'])
def view_albums():
    table = dynamodb.Table(albums_table)
    try:
        response = table.scan()
        if (response['Count'] == 0):
            return {'error': 'Albums not found'.format(album_id)}, 500
        else:
            album_set = { a['id']: {
                'id': a['id'], 
                'nb_images': len(a['images']), 
                'gallery': a['galleries'][-1], 
                'title': a['title'], 
                'timestamp': a['timestamp'] 
            } for a in response['Items'] }
            albums = sorted(album_set.values(), key=lambda a: a['timestamp'])[::-1]
            return render_template('list.html', albums=albums)
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>', methods = ['GET'])
def edit_album(album_id):
    table = dynamodb.Table(albums_table)
    try:
        albums_matching_query = table.query(KeyConditionExpression=Key('id').eq(album_id))
        if (albums_matching_query['Count'] == 0):
            return {'error': 'Album "{}" not found'.format(album_id)}, 404
        else:
            most_recent_album = albums_matching_query['Items'][-1]
            album_view = make_album_view(most_recent_album)
            pprint(most_recent_album)
            return render_template('album.html', album=album_view, msg="")
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>', methods = ['POST'])
def submit_album(album_id):
    form_result = request.form
    files = request.files
    table = dynamodb.Table(albums_table)
    try:
        cur_album = parse_album(form_result, album_id)
        new_images = upload_files(files, album_id)
        new_album = upload(cur_album, new_images)
        album_view = make_album_view(new_album)
        return render_template('album.html', album=album_view, msg="Album successfully saved")
    except ClientError as e:
        return {'error': e}, 500

def make_album_view(album):
    images = [{**im, 
        'size': ",".join([str(s) for s in im['size']]),
        'published': im.get('published', True)
    } for im in album['images']]
    return {**album, 'images': enumerate(images) }

def parse_album(res, url):
    unordered_images = [parse_image(im, res) for im in res.getlist('images[]')]
    ordered_images = sorted(unordered_images, key=lambda im: float(im[0]))
    pprint(ordered_images)
    images = [im[1] for im in ordered_images]
    return {
        'title': res['title'],
        'url': url,
        'galleries': ['all', res['gallery']],
        'description': res['description'],
        'public': res['public'] is 'true',
        'images': images
    }

def parse_image(image_name, res):
    d = { key.split("-")[0]: val for key, val in res.items() if image_name in key }
    pprint(d)
    order = d['order']
    fmt = "%Y-%m-%dT%H:%M:%S"
    return order, {
        'description': d['description'],
        'file': image_name,
        'banner': d['banner'] == 'true',
        'size': [int(s) for s in d['size'].split(",")],
        'cover': d['cover'] == 'true',
        'published': d['published'] == 'true',
        'datetime': d['datetime']
    }

def upload(album, new_images):
    # Clean config of empty strings
    for key, val in album.items():
        if val == "":
            album[key] = None

    images = album['images'] + new_images
    pprint(images)
    for im in images:
        for key, val in im.items():
            if val == "":
                im[key] = None

    # Upload config to dynamoDB
    table = dynamodb.Table(albums_table)
    album_config = { 
        'id': album['url'], 
        'timestamp': int(datetime.now().timestamp()), 
        **album,
        'images': images }
    try:
        table.put_item(Item=album_config)
    except ClientError as e:
        print(e)
    return album_config

def acceptable_image(filename):
    print("Testing {}".format(filename))
    res = (filename != '') and (filename.lower()[-3:] == "jpg")
    print("Result was {}".format(res))
    return res


def resize(image_path, new_width, new_height, temp_dir):
    image_orig = Image.open(image_path)
    image = image_orig.copy()
    image_name = image_path.lower().split(".jpg")[0].split("/")[-1]
    orientation = 'horizontal' if image_orig.size[0] > image_orig.size[1] else 'vertical'

    if new_width == new_height:
        (width, height) = image.size
        if orientation == 'horizontal':
            margin = (width - height) / 2
            image = image.crop((margin, 0, width - margin, height))
        else:
            margin = (height - width) / 2
            image = image.crop((0, margin, width, height - margin))

    image.thumbnail((new_width, new_height), Image.ANTIALIAS)
    image_path = "%s/%s_%ix%i.jpg" % (temp_dir, image_name, new_width, new_height)
    image.save(image_path, "JPEG", quality=92)
    return image_path

def upload_files(files, album_id):
    images = files.getlist('new-images')
    temp_dir = tempfile.mkdtemp()
    response = s3.list_objects(Bucket=images_bucket, Prefix="albums/{}".format(album_id))

    image_conf = []
    for im in images:
        if not acceptable_image(im.filename):
            continue

        path = os.path.join(temp_dir, im.filename)
        im.save(path)
        for (width, height) in image_sizes:
            resized_path = resize(path, width, height, temp_dir)
            upload_s3(im.filename, album_id, temp_dir, images_bucket)

        original_file = "{}_original.jpg".format(im.filename[:-4])
        original_path = "{}/{}".format(temp_dir, original_file)
        Image.open(path).save(original_path, "JPEG", quality=92)
        upload_s3(original_file, album_id, temp_dir, images_bucket)

        conf = image_info(temp_dir, im.filename, "", published = False)
        conf['size'] = [conf['size'][0], conf['size'][1]]
        image_conf.append(conf)

    return image_conf

