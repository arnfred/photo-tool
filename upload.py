from flask import Flask, escape, request, render_template
import pathlib
import boto3
import os
import tempfile
from functools import reduce
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from pprint import pprint
from datetime import datetime
from werkzeug.utils import secure_filename
from photos import image_sizes, upload_s3, image_info
from videos import video_info, extract_thumb
from PIL import Image

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
images_bucket = os.environ['IMAGES_BUCKET']
albums_table = os.environ['ALBUMS_TABLE']
galleries_table = os.environ['GALLERIES_TABLE']
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
    try:
        galleries_response = dynamodb.Table(galleries_table).scan()
        galleries = galleries_response['Items']
        albums_matching_query = dynamodb.Table(albums_table).query(KeyConditionExpression=Key('id').eq(album_id))
        if (albums_matching_query['Count'] == 0):
            album = new_album(album_id)
            album_view = make_album_view(album)
            return render_template('album.html', album=album_view, galleries=galleries, msg="Create new album")
        else:
            most_recent_album = albums_matching_query['Items'][-1]
            album_view = make_album_view(most_recent_album)
            return render_template('album.html', album=album_view, galleries=galleries, msg="")
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>/save', methods = ['POST'])
def album_save(album_id):
    form_result = request.form
    try:
        cur_album = parse_album(form_result, album_id)
        album_config = make_album_config(cur_album)
        upload_album(album_config)
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Album successfully saved")
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>/upload', methods = ['POST'])
def album_upload(album_id):
    form_result = request.form
    files = request.files
    try:
        cur_album = parse_album(form_result, album_id)
        new_media = upload_files(files, album_id)
        album_config = make_album_config(cur_album, new_media)
        upload_album(album_config)
        album_view = make_album_view(album_config, new_media)
        return render_template('album.html', album=album_view, msg="Pictures successfully uploaded")
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>/reorder', methods = ['POST'])
def album_reorder(album_id):
    form_result = request.form
    try:
        cur_album = parse_album(form_result, album_id)
        album_config = make_album_config(cur_album)
        album_config['images'] = sorted(album_config['images'], key=lambda im: im['datetime'])
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Album Images Reordered")
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>/remove/<image_id>', methods = ['POST'])
def image_remove(album_id, image_id):
    form_result = request.form
    try:
        cur_album = parse_album(form_result, album_id)
        album_config = make_album_config(cur_album)
        album_config['images'] = [im for im in album_config['images'] if im['file'] != image_id]
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Removed Image: " + image_id)
    except ClientError as e:
        return {'error': e}, 500

@app.route('/gallery/<gallery_id>', methods = ['GET'])
def edit_gallery(gallery_id):
	try:
		galleries_matching_query = dynamodb.Table(galleries_table).query(KeyConditionExpression=Key('id').eq(gallery_id))
		if (galleries_matching_query['Count'] == 0):
			gallery = new_gallery(gallery_id)
			gallery_view = make_gallery_view(gallery)
			return render_template('gallery.html', gallery=gallery_view, msg="Create new gallery")
		else:
			most_recent_gallery = galleries_matching_query['Items'][-1]
			gallery_view = make_gallery_view(most_recent_gallery)
			return render_template('gallery.html', gallery=gallery_view, msg="")
	except ClientError as e:
		return {'error': e}, 500

@app.route('/gallery/<gallery_id>', methods = ['POST'])
def submit_gallery(gallery_id):
    cur_gallery = request.form
    table = dynamodb.Table(galleries_table)
    try:
        new_gallery = upload_gallery(cur_gallery)
        gallery_view = make_gallery_view(new_gallery)
        return render_template('gallery.html', gallery=gallery_view, msg="Gallery successfully saved")
    except ClientError as e:
        return {'error': e}, 500

def make_album_view(album, new_images = []):
    new_files = set([im['file'] for im in new_images])
    images = [(i+1, {
		**im, 
        'size': ",".join([str(s) for s in im['size']]),
        'description': im['description'].strip() if im['description'] else "",
        'published': True if im['file'] in new_files else im.get('published', True),
	'is_video': im.get('is_video', False)
        }) for i, im in enumerate(album['images'])]
    return {
		**album, 
		'description': album['description'].strip() if album['description'] else "",
		'images': images
	}

def make_gallery_view(gallery):
	return {
		**gallery,
		'description': gallery['description'].strip()
	}

def parse_album(res, url):
    unordered_images = [parse_image(im, res) for im in res.getlist('images[]')]
    ordered_images = sorted(unordered_images, key=lambda im: float(im[0]))
    images = [im[1] for im in ordered_images]
    return {
            'title': res['title'],
            'url': url,
            'galleries': ['all', res['gallery']],
            'description': res['description'],
            'public': res.get('public') == 'true',
            'images': images
            }

def new_album(album_id):
    return {
            'id': album_id,
            'title': '',
            'url': album_id,
            'galleries': ['all', 'gallery-name'],
            'description': '',
            'public': True,
            'images': []
            }

def new_gallery(gallery_id):
    return {
	        'id': gallery_id,
			'url': gallery_id,
			'description': ''
			}

def parse_image(image_name, res):
    d = { key.split("-")[0]: val for key, val in res.items() if image_name in key }
    order = d.get('order', 0)
    fmt = "%Y-%m-%dT%H:%M:%S"
    return order, {
            'description': d['description'],
            'file': image_name,
            'banner': d.get('banner') == 'true',
            'size': [int(s) for s in d['size'].split(",")],
            'cover': d.get('cover') == 'true',
            'published': d.get('published') == 'true',
            'is_video': d.get('is_video') == 'True',
            'datetime': d['datetime']
            }

def upload_gallery(gallery):
    # Clean config of empty strings
    for key, val in gallery.items():
        if val == "":
            gallery[key] = None

    # Upload config to dynamoDB
    table = dynamodb.Table(galleries_table)
    gallery_config = { 
			**gallery,
			'id': gallery['url']
	}
    try:
        table.put_item(Item=gallery_config)
    except ClientError as e:
        print(e)
    return gallery_config

def make_album_config(album, new_images = []):
    # Clean config of empty strings
    for key, val in album.items():
        if val == "":
            album[key] = None

    all_images = album['images'] + new_images
    file_names = lambda image_list: set([im['file'] for im in image_list])
    images = list(reduce(lambda l, im: l if im['file'] in file_names(l) else l+[im], all_images, []))
    for im in images:
        if isinstance(im['datetime'], str):
            pass
        elif im['datetime'] is None:
            im['datetime'] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        else:
            im['datetime'] = im.get('datetime', datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")
        for key, val in im.items():
            if val == "":
                im[key] = None
    return { 
        'id': album['url'], 
        'timestamp': int(datetime.now().timestamp()), 
        **album,
        'images': images }

def upload_album(album_config):
    table = dynamodb.Table(albums_table)
    try:
        table.put_item(Item=album_config)
    except ClientError as e:
        print(e)

def acceptable_image(filename):
    print("Testing if '{}' is a jpg file".format(filename))
    res = (filename != '') and (filename.lower()[-3:] == "jpg")
    print("Result was {}".format(res))
    return res

def acceptable_video(filename):
    print("Testing if '{}' is an mp4 file".format(filename))
    res = (filename != '') and (filename.lower()[-3:] == "mp4")
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
    resized_name = "%s_%ix%i.jpg" % (image_name, new_width, new_height)
    image_path = "%s/%s" % (temp_dir, resized_name)
    print("Saving '{}' to '{}'".format(image_name, image_path))
    image.save(image_path, "JPEG", quality=92)
    return resized_name

def upload_files(files, album_id):
    media = files.getlist('new-media')
    temp_dir = tempfile.mkdtemp()
    response = s3.list_objects(Bucket=images_bucket, Prefix="albums/{}".format(album_id))

    media_conf = []
    for medium in media:
        if acceptable_image(medium.filename):
            path = os.path.join(temp_dir, medium.filename)
            medium.save(path)
            for (width, height) in image_sizes:
                resized_name = resize(path, width, height, temp_dir)
                upload_s3(resized_name, album_id, temp_dir, images_bucket)

            original_file = "{}_original.jpg".format(medium.filename[:-4])
            original_path = os.path.join(temp_dir, original_file)
            Image.open(path).save(original_path, "JPEG", quality=92)
            upload_s3(original_file, album_id, temp_dir, images_bucket)

            conf = image_info(temp_dir, medium.filename, "", published = False)
            conf['size'] = [conf['size'][0], conf['size'][1]]
            media_conf.append(conf)

        elif acceptable_video(medium.filename):
            filename = medium.filename.lower()
            path = os.path.join(temp_dir, filename)
            medium.save(path)
            upload_s3(filename, album_id, temp_dir, images_bucket)

            conf = video_info(temp_dir, medium.filename.lower(), "", published = False)
            media_conf.append(conf)

            # Save thumbnail
            thumb_name = "{}.jpg".format(filename[:-4])
            thumb_path = os.path.join(temp_dir, thumb_name)
            extract_thumb(path, thumb_path, conf['size'][0])
            for (width, height) in image_sizes:
                resized_name = resize(thumb_path, width, height, temp_dir)
                upload_s3(resized_name, album_id, temp_dir, images_bucket)

            # Save thumb original
            thumb_original_file = "{}_original.jpg".format(thumb_name[:-4])
            thumb_original_path = os.path.join(temp_dir, thumb_original_file)
            Image.open(thumb_path).save(thumb_original_path, "JPEG", quality=92)
            upload_s3(thumb_original_file, album_id, temp_dir, images_bucket)

    return media_conf


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='127.0.0.1', port=port)
