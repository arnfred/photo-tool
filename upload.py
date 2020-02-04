from flask import Flask, escape, request, render_template
import boto3
import os
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from pprint import pprint
from datetime import datetime
from werkzeug.utils import secure_filename

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
images_bucket = os.environ['IMAGES_BUCKET']
albums_table = os.environ['ALBUMS_TABLE']
app = Flask(__name__)

@app.route('/album/<album_id>', methods = ['GET'])
def edit_album(album_id):
    table = dynamodb.Table(albums_table)
    try:
        albums_matching_query = table.query(KeyConditionExpression=Key('id').eq(album_id))
        if (albums_matching_query['Count'] == 0):
            return {'error': 'Album "{}" not found'.format(album_id)}, 404
        else:
            most_recent_album = albums_matching_query['Items'][-1]
            album_view = make_printable(most_recent_album)
            return render_template('album.html', album=album_view, msg="")
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>', methods = ['POST'])
def submit_album(album_id):
    form_result = request.form
    files = request.files
    table = dynamodb.Table(albums_table)
    try:
        album = parse_album(form_result, album_id)
        album_view = make_printable(album)
        upload(album)
        upload_files(files)
        return render_template('album.html', album=album_view, msg="Album successfully saved")
    except ClientError as e:
        return {'error': e}, 500

def make_printable(album):
    return {**album, 'images': [{**im, 'size': ",".join([str(s) for s in im['size']]) } for im in album['images']] }

def parse_album(res, url):
    images = [parse_image(im, res) for im in res.getlist('images[]')]
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
    fmt = "%Y-%m-%dT%H:%M:%S"
    return {
        'description': d['description'],
        'file': image_name,
        'banner': d['banner'] == 'true',
        'size': [int(s) for s in d['size'].split(",")],
        'cover': d['cover'] == 'true',
        'datetime': datetime.strptime(d['datetime'], fmt).strftime(fmt)
    }

def upload(album):
    # Clean config of empty strings
    for key, val in album.items():
        if val == "":
            album[key] = None
    for im in album['images']:
        for key, val in im.items():
            if val == "":
                im[key] = None

    # Upload config to dynamoDB
    table = dynamodb.Table(albums_table)
    album_config = { 'id': album['url'], 'timestamp': int(datetime.now().timestamp()), **album }
    try:
        pprint(album_config)
        #table.put_item(Item=album_config)
    except ClientError as e:
        print(e)


def upload_files(files):
    print(files)



