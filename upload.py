from flask import Flask, escape, request, render_template
from flask_simplelogin import SimpleLogin, is_logged_in, login_required
from hashlib import sha256
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
from photos import image_sizes, upload_s3, image_info, image_size
from videos import video_info, extract_thumb, reencode_to_mp4
from PIL import Image

s3 = boto3.resource('s3')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
images_bucket = os.environ['IMAGES_BUCKET']
albums_table = os.environ['ALBUMS_TABLE']
galleries_table = os.environ['GALLERIES_TABLE']
app = Flask(__name__)
SimpleLogin(app)
ALBUM_PASSWORD_STARS = "*********"


@app.route('/', methods=['GET'])
@login_required
def view_albums():
    table = dynamodb.Table(albums_table)
    try:
        response = table.scan()
        if (response['Count'] == 0):
            return {'error': 'Albums not found'.format(album_id)}, 500
        else:
            album_set = {a['id']: {
                'id': a['id'], 
                'nb_images': len(a['images']), 
                'gallery': a['galleries'][-1], 
                'title': a['title'], 
                'timestamp': a['timestamp'] 
            } for a in response['Items']}
            albums = sorted(album_set.values(), key=lambda a: a['timestamp'])[::-1]
            return render_template('list.html', albums=albums)
    except ClientError as e:
        return {'error': e}, 500


@app.route('/album/<album_id>', methods=['GET'])
@login_required
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


@app.route('/album/<album_id>/save', methods=['POST'])
@login_required
def album_save(album_id):
    form_result = request.form
    try:
        album_config = parse_album_config(form_result, album_id)
        upload_album(album_config)
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Album successfully saved")
    except ClientError as e:
        return {'error': e}, 500


@app.route('/album/<album_id>/upload', methods=['POST'])
@login_required
def album_upload(album_id):
    form_result = request.form
    files = request.files
    try:
        new_media = upload_files(files, album_id)
        album_config = parse_album_config(form_result, album_id, new_media)
        upload_album(album_config)
        album_view = make_album_view(album_config, new_media)
        return render_template('album.html', album=album_view, msg="Pictures successfully uploaded")
    except ClientError as e:
        return {'error': e}, 500


@app.route('/album/<album_id>/reorder', methods=['POST'])
@login_required
def album_reorder(album_id):
    form_result = request.form
    try:
        album_config = parse_album_config(form_result, album_id)
        album_config['images'] = sorted(album_config['images'], key=lambda im: im['datetime'])
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Album Images Reordered")
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>/remove/<image_id>', methods = ['POST'])
@login_required
def image_remove(album_id, image_id):
    form_result = request.form
    try:
        album_config = parse_album_config(form_result, album_id)
        album_config['images'] = [im for im in album_config['images'] if im['file'] != image_id]
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Removed Image: " + image_id)
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>/fix_originals', methods = ['POST'])
@login_required
def fix_originals(album_id):
    form_result = request.form
    try:
        album_config = parse_album_config(form_result, album_id)
        fixed = [fix_original_image(im, album_id) for im in album_config['images']]
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Fixed following images: {}".format(fixed))
    except ClientError as e:
        return {'error': e}, 500

@app.route('/album/<album_id>/fix_jpegs', methods = ['POST'])
@login_required
def fix_jpegs(album_id):
    form_result = request.form
    try:
        album_config = parse_album_config(form_result, album_id)
        fixed = [fix_trailing_file_extension(im, album_id) for im in album_config['images']]
        album_config['images'] = fixed
        upload_album(album_config)
        album_view = make_album_view(album_config)
        return render_template('album.html', album=album_view, msg="Fixed jpeg extension of following images: {}".format([im['file'] for im in fixed]))
    except ClientError as e:
        return {'error': e}, 500

@app.route('/gallery/<gallery_id>', methods = ['GET'])
@login_required
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
@login_required
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
        'image_url': generate_presigned_url(album['id'], im, False),
        'video_url': generate_presigned_url(album['id'], im, True),
        'published': True if im['file'] in new_files else im.get('published', True),
	'is_video': im.get('is_video', False)
        }) for i, im in enumerate(album['images'])]
    return {
		**album, 
		'description': album['description'].strip() if album['description'] else "",
		'secret': album.get('secret', ""),
		'password': ALBUM_PASSWORD_STARS if album.get('secret', False) else "",
		'images': images
	}

def make_gallery_view(gallery):
	return {
		**gallery,
		'description': gallery['description'].strip()
	}



def parse_album_config(res, url, new_images = []):
    unordered_images = [parse_image(im, res) for im in res.getlist('images[]')]
    ordered_images = sorted(unordered_images, key=lambda im: float(im['order']))
    all_images = ordered_images + new_images
    images = list({im['file']: im for im in all_images}.values())
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
                
    config = {'title': res['title'],
              'id': url,
              'timestamp': int(datetime.now().timestamp()), 
              'url': url,
              'galleries': ['all', res['gallery']],
              'description': res['description'],
              'public': res.get('public') == 'true',
              'secret': make_secret(url, res['secret'], res['password']),
              'images': images}

    # Clean config of empty strings
    for key, val in config.items():
        if val == "":
            config[key] = None

    return config



def make_secret(url, old_secret, password):
    if password == "" or password == ALBUM_PASSWORD_STARS:
        return old_secret
    else:
        new_secret = sha256((password + url).encode('utf-8')).hexdigest()
        return new_secret



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
    pprint(res)
    d = { key.split("-")[0]: val for key, val in res.items() if image_name in key }
    order = d.get('order', 0)
    fmt = "%Y-%m-%dT%H:%M:%S"
    return {'order': order,
            'description': d['description'],
            'file': image_name,
            'banner': d.get('banner') == 'true',
            'size': [int(s) for s in d['size'].split(",")],
            'cover': d.get('cover') == 'true',
            'published': d.get('published') == 'true',
            'is_video': d.get('is_video') == 'True',
            'datetime': d['datetime']}

def upload_gallery(gallery):
    # Clean config of empty strings
    for key, val in gallery.items():
        if val == "":
            gallery[key] = None

    # Upload config to dynamoDB
    table = dynamodb.Table(galleries_table)
    gallery_config = { 
        **gallery,
        'timestamp': int(datetime.now().timestamp()), 
        'id': gallery['url']
	}
    try:
        table.put_item(Item=gallery_config)
    except ClientError as e:
        print(e)
    return gallery_config

def upload_album(album_config):
    table = dynamodb.Table(albums_table)
    try:
        table.put_item(Item=album_config)
    except ClientError as e:
        print(e)

def acceptable_image(filename):
    print("Testing if '{}' is a jpg file".format(filename))
    ext = filename.lower().split(".")[-1]
    res = (filename != '') and (ext == "jpg") or (ext == "jpeg")
    print("Result was {}".format(res))
    return res

def acceptable_video(filename):
    print("Testing if '{}' is an mp4 or mov file".format(filename))
    ext = filename.lower().split(".")[-1]
    res = (filename != '') and ((ext == "mp4") or (ext == "mov") or (ext == "m4a"))
    print("Result was {}".format(res))
    return res

def image_size_name(image_name, width, height):
    return "%s_%ix%i.jpg" % (image_name, width, height)

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
    resized_name = image_size_name(image_name, new_width, new_height)
    image_path = "%s/%s" % (temp_dir, resized_name)
    print("Saving '{}' to '{}'".format(image_name, image_path))
    image.save(image_path, "JPEG", quality=92)
    return resized_name

def upload_files(files, album_id):
    media = files.getlist('new-media')
    temp_dir = tempfile.mkdtemp()

    media_conf = []
    for medium in media:
        if acceptable_image(medium.filename):
            filepath = medium.filename.lower()
            path = os.path.join(temp_dir, filepath)
            medium.save(path)
            for (width, height) in image_sizes:
                resized_name = resize(path, width, height, temp_dir)
                upload_s3(resized_name, album_id, temp_dir, images_bucket)

            
            filename = "".join(filepath.split(".")[:-1])
            original_file = "{}_original.jpg".format(filename)
            original_path = os.path.join(temp_dir, original_file)
            Image.open(path).save(original_path, "JPEG", quality=92)
            upload_s3(original_file, album_id, temp_dir, images_bucket)

            conf = image_info(temp_dir, filepath, "", published = False)
            conf['size'] = [conf['size'][0], conf['size'][1]]
            media_conf.append(conf)

        elif acceptable_video(medium.filename):
            filepath = medium.filename.lower()
            path = os.path.join(temp_dir, filepath)
            medium.save(path)
            mp4_filename = reencode_to_mp4(filepath, temp_dir)
            mp4_path = os.path.join(temp_dir, mp4_filename)
            upload_s3(mp4_filename, album_id, temp_dir, images_bucket)

            conf = video_info(temp_dir, filepath, "", published = False)

            # Save thumbnail
            thumb_filename = "".join(mp4_filename.split(".")[:-1])
            thumb_name = "{}.jpg".format(thumb_filename)
            thumb_path = os.path.join(temp_dir, thumb_name)
            extract_thumb(mp4_path, thumb_path, conf['size'][0])
            thumb_size = image_size(thumb_path)
            for (width, height) in image_sizes:
                resized_name = resize(thumb_path, width, height, temp_dir)
                upload_s3(resized_name, album_id, temp_dir, images_bucket)

            # Save thumb original
            thumb_original_file = "{}_original.jpg".format(thumb_filename)
            thumb_original_path = os.path.join(temp_dir, thumb_original_file)
            Image.open(thumb_path).save(thumb_original_path, "JPEG", quality=92)
            upload_s3(thumb_original_file, album_id, temp_dir, images_bucket)

            # Set media_conf size to thumb size
            conf['size'] = [thumb_size[0], thumb_size[1]]
            media_conf.append(conf)

    return media_conf

def fix_trailing_file_extension(image, album_id):
    # Correcting all sizes of images
    old_file = image['file']
    new_file = image['file'].replace(".jpeg", "")
    for (width, height) in image_sizes:
        old_filename = image_size_name(old_file, width, height)
        old_key = f"albums/{album_id}/{old_filename}"
        new_filename = image_size_name(new_file, width, height)
        new_key = f"albums/{album_id}/{new_filename}"
        try:
            s3.Object(bucket_name=images_bucket, key=new_key).get()
            print("Original already correctly stored: {}".format(new_key))
        except ClientError:
            print("Copying {} to {}".format(old_key, new_key))
            s3.Object(images_bucket, new_key).copy_from(CopySource={'Bucket': images_bucket, 'Key': old_key})

    # correcting original image (e.g. img_5328._original.jpg)
    old_key = f"albums/{album_id}/{old_file.replace("jpeg", "")}_original.jpg"
    new_key = f"albums/{album_id}/{new_file}_original.jpg"
    try:
        s3.Object(bucket_name=images_bucket, key=new_key).get()
        print("Original already correctly stored: {}".format(new_key))
    except ClientError:
        print("Copying {} to {}".format(old_key, new_key))
        s3.Object(images_bucket, new_key).copy_from(CopySource={'Bucket': images_bucket, 'Key': old_key})

    image['file'] = new_file
    return image

def fix_original_image(image, album_id):
    old_key = "albums/{}/{}_original.jpg".format(album_id, image['file'].upper())
    new_key = "albums/{}/{}_original.jpg".format(album_id, image['file'].lower())
    try:
        s3.Object(bucket_name=images_bucket, key=new_key).get()
        print("Original already correctly stored: {}".format(new_key))
        return ""
    except ClientError:
        print("Copying {} to {}".format(old_key, new_key))
        try:
            s3.Object(images_bucket, new_key).copy_from(CopySource={'Bucket': images_bucket, 'Key': old_key})
            return new_key
        except ClientError as ex:
            print("client error: {}".format(ex))
            return ""

def generate_presigned_url(album_id, image, use_video):
    image_key = "albums/{}/{}_800x600.jpg".format(album_id, image['file'])
    video_key = "albums/{}/{}.mp4".format(album_id, image['file'])
    if use_video:
        key = video_key
    else:
        key = image_key
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': images_bucket,
                                                            'Key': key},
                                                    ExpiresIn=60*5)
    except ClientError as e:
        print(e)
        return None

    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='127.0.0.1', port=port)
