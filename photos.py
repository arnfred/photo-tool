#!/usr/bin/python

import os
import fnmatch
import pprint
import json
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime
from subprocess import call
from dateutil import parser
import urllib.request, urllib.parse, urllib.error
import sys
import getopt
import traceback
import toml
import boto3
import time

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Create thumbnails of the following sizes
thumb_sizes = [(2000, 1500), (1600, 1200), (1280, 980), (1024, 768), (800, 600), (600, 450), (400, 300), (150, 150)]

def main(prog_name, argv):

    # Check that a command is given
    if len(argv) > 0:
        command = argv[0]

        # Check that the command is one of the commands we support
        if command == 'init':
            main_album(prog_name, argv[1:])
        elif command == 'gallery':
            main_gallery(prog_name, argv[1:])
        elif command == 'convert':
            main_toml_convert(prog_name, argv[1:])
        elif command == 'publish':
            main_publish(prog_name, argv[1:])
        else:
            print(("""You need to specify a command:
                %s init [args]
                %s gallery [args]
                %s publish [args]""" % (prog_name, prog_name, prog_name)))
            sys.exit(2)


def main_album(prog_name, argv):

    # Get command line options
    try:
        opts, args = getopt.getopt(argv, "n:p:f", ["name=", "path=", "conf_name="])
        opts_dict = dict(opts)

        # find arguments
        album_name = opts_dict.get("--name", opts_dict["-n"])
        album_path = opts_dict.get("--path", opts_dict.get("-p", "."))
        conf_name = opts_dict.get("--conf_name", "album.toml")
        force = "-f" in args
        init_album(album_name, album_path, force, conf_name = conf_name, cmd = prog_name)

    # In case we get unexpected arguments
    except getopt.GetoptError:
        print("Malformed option. Use:")
        print(("""%s album -n <name> [-p <path> [-f [--conf_name <album.toml>]]]""" % (prog_name)))
        sys.exit(2)
    except KeyError as ke:
        print(("Missing argument: %s" % ke))
        print(("""%s album -n <name> [-p <path> [-f [--conf_name <album.toml>]]]""" % (prog_name)))
        sys.exit(2)


def main_gallery(prog_name, argv):

    # Get command line options
    try:
        opts, args = getopt.getopt(argv,"rn:p:d:u",["name=","path=","desc=","description=", "upload", "conf_name=", "remove"])
        opts_dict = dict(opts)

        # find arguments
        gallery_name = opts_dict.get("--name", opts_dict.get("-n"))
        gallery_path = opts_dict.get("--path", opts_dict.get("-p", "."))
        conf_name = opts_dict.get("--conf_name", "galleries.conf")

        if gallery_name != None:

            # Do we delete?
            if "-r" in list(opts_dict.keys()) or "--remove" in list(opts_dict.keys()):
                remove_gallery(gallery_path, gallery_name)
            else:
                # Get description
                gallery_desc = opts_dict.get("--description", opts_dict.get("--desc", opts_dict["-d", ""]))
                add_gallery(gallery_path, gallery_name, gallery_desc, conf_name = conf_name)

        # Push online?
        if "-u" in list(opts_dict.keys()) or "--upload" in list(opts_dict.keys()):
            process_galleries(gallery_path, conf_name)

    # In case we get unexpected arguments
    except getopt.GetoptError:
        print("Malformed option. Use:")
        print(("""%s gallery -n <name> [-p <path> [-d <description> [--conf_name <album.conf> [--upload]]]]""" % (prog_name)))
        sys.exit(2)
    except KeyError as ke:
        print(("Missing argument: %s" % ke))
        print(("""%s gallery -n <name> [-p <path> [-d <description> [--conf_name <album.conf> [--upload]]]]""" % (prog_name)))
        sys.exit(2)

def main_toml_convert(prog_name, argv):

    # Get command line options
    try:
        opts, args = getopt.getopt(argv,"d:s:w:q:k:",["directory=","skip=","temp_dir=","keep_conf="])
        opts_dict = dict(opts)

        # find arguments
        directory = opts_dict.get("--directory", opts_dict.get("-d", "."))
        skip = opts_dict.get("--skip", opts_dict.get("-s", "galleries.conf")).split(",")
        dry_run = "-q" in list(opts_dict.keys())
        keep_conf = "-k" in list(opts_dict.keys())

        convert(directory, skip = skip, dry_run = dry_run, keep_conf = keep_conf)

    # In case we get unexpected arguments
    except getopt.GetoptError:
        print("Malformed option. Use:")
        print(("""%s convert -d <directory> [-s <conf files to skip> [-q <Toggle dry-run>]]""" % (prog_name)))
        sys.exit(2)
    except KeyError as ke:
        print(("Missing argument: %s" % ke))
        print(("""%s convert -d <directory> [-s <conf files to skip>]""" % (prog_name)))
        sys.exit(2)



def main_publish(prog_name, argv):

    # Get command line options
    try:
        opts, args = getopt.getopt(argv,"d:s:wkt:",["directory=","thumbnails=","skip=","temp_dir=","keep_temp="])
        opts_dict = dict(opts)

        # find arguments
        directory = opts_dict.get("--directory", opts_dict["-d"])
        temp_dir = opts_dict.get("--temp_dir", opts_dict.get("-t", "tmp"))
        skip = opts_dict.get("--skip", opts_dict.get("-s", "galleries.conf")).split(",")
        keep_temp = "-k" in list(opts_dict.keys())
        write_thumbnails = "-w" in list(opts_dict.keys())

        publish(directory, temp_dir = temp_dir, write_thumbnails = write_thumbnails, skip = skip, keep_temp = keep_temp, program_name = prog_name)

    # In case we get unexpected arguments
    except getopt.GetoptError:
        print("Malformed option. Use:")
        print(("""%s publish -d <directory> [-o <temp directory> [-s <conf files to skip> [-w <write thumbnails>]]]""" % (prog_name)))
        sys.exit(2)
    except KeyError as ke:
        print(("Missing argument: %s" % ke))
        print(("""%s publish -d <directory> [-o <temp directory> [-s <conf files to skip> [-w <write thumbnails>]]]""" % (prog_name)))
        sys.exit(2)


def get_images(directory):
    """ Get images in all subfolders of directory """
    # Recursively explore directory and return all images
    images = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if fnmatch.fnmatch(f.lower(), "*.jpg"):
                images.append(f)

        if '.git' in dirs:
            dirs.remove('.git')  # don't visit git directories
    return list(sorted(images))


def find_image(directory, name):
    """ Returns the first image in subdirectories of directory that matches name """
    # find the exact location of a filename that might reside in the subfolder of the root
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.lower() == name.lower():
                return "%s/%s" % (root, f)

        if '.git' in dirs:
            dirs.remove('.git')  # don't visit git directories
    return None


# First task: Init the album.conf file
def init_album(album_name, album_path, force = False, conf_name = "album.toml", cmd = "photos"):
    """ Inits an album.conf file in the directory with slots ready to be filled out """

    # Does directory exist?
    if not os.path.exists(album_path):
        # Return errorinit_album("Trip to Bako", "data/2013-07-26 Kuching/")
        print(("'%s' doesn't exist" % (album_path)))
        return -1

    # Does album.conf already exist?
    conf_path = "%s/%s" % (album_path, conf_name)
    if os.path.isfile(conf_path) and not force:
        # If album.conf exists and we don't want to overwrite it, give error
        print(("'%s' already exists.\nIf you want to overwrite, use \"%s album -f \"%s\" \"%s\"" % (conf_path, cmd, album_name, album_path)))
        return -1

    # Create album.conf
    else:
        # Get information
        album_url = urllib.parse.quote_plus(album_name.lower().replace(" ","-"))
        to_image = lambda file_name : image_info(album_path, file_name, "")
        album = {
                'title': album_name,
                'public': True,
                'description': "",
                'url': album_url,
                'galleries': ["all"],
                'images': list(map(to_image, get_images(album_path)))
        }

        # Create album.toml file
        with open(conf_path, 'w') as f:
            toml.dump(album, f)



def add_gallery(galleries_path, gallery_name, gallery_desc = "", conf_name = "galleries.conf"):
    """ Adds gallery line to galleries.conf file """

    # Load gallery file
    conf_path = "%s/%s" % (galleries_path, conf_name)
    if os.path.isfile(conf_path):
        with open(conf_path, 'r') as conf:
            lines = conf.readlines()
    else:
        print(("Error: %s doesn't exist" % conf_path))
        sys.exit(2)

    # Compile new gallery configuration
    gallery_conf = "%s :: \"%s\"" % (gallery_name, gallery_desc)

    # Replace existing configuration or add to end of list
    has_gallery = False
    for i,l in enumerate(lines):
        if l.split(" :: ")[0].lower() == gallery_name.lower():
            lines[i] = "%s\n" % gallery_conf
            has_gallery = True
            if not has_gallery:
                lines.append("%s" % gallery_conf)

    # Save file
    with open(conf_path, 'w') as conf:
        conf.write("".join(lines))


def remove_gallery(galleries_path, gallery_name, conf_name = "galleries.conf"):
    # Load gallery file
    conf_path = "%s/%s" % (galleries_path, conf_name)
    if os.path.isfile(conf_path):
        with open(conf_path, 'r') as conf:
            lines = conf.readlines()
    else:
        print("Error: Can't remove lines from empty file")
        sys.exit(2)

    # Remove lines
    new_lines = [l for l in lines if l.split(" :: ")[0].lower() != gallery_name.lower()]

    # Save file
    with open(conf_path, 'w') as conf:
        conf.write("".join(new_lines))


def get_confs(directory, extension = "toml"):
    """ Recursively explore directory and return all images """
    confs = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if fnmatch.fnmatch(f.lower(), "*.%s" % extension):
                confs.append((root, f))

        if '.git' in dirs:
            dirs.remove('.git')  # don't visit git directories
    return confs


def image_size(image_path):
    """ get image size """
    image = Image.open(image_path)
    return image.size


def image_exif(image_path, valid_tags = ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']):
    """ Returns the exif data from a given image """
    image = Image.open(image_path)
    info = image._getexif()
    exif = {}
    if info == None : return exif
    for tag, value in list(info.items()):
        decoded = TAGS.get(tag, tag)
        if decoded in valid_tags or isinstance(value, str):
            value = value.strip().partition("\x00")[0]
            if isinstance(decoded, str) and decoded.startswith("DateTime"):
                value_date = parser.parse(value.replace(":",""))
                exif[decoded] = value_date
    return exif


def image_info(root, image_name, desc):
    """ Generate a dictionary of information about an image """
    # Init image dictionary
    image_dict = {
        'file' : image_name.lower().split(".jpg")[0],
        'description' : desc.strip(" *"),
        'cover' : len(desc) > 1 and desc[-1] == '*',
        'banner' : len(desc) > 2 and desc[-2] == '*'
    }

    # Find image
    image_path = find_image(root, image_name)
    if image_path == None:
        raise Exception("Image %s doesn't exist in %s" % (image_name, root))

    # Define what exif data we are interested in and how it is translated
    exif = image_exif(image_path)
    size = image_size(image_path)

    # Now pull the interesting data
    image_dict['datetime'] = exif.get('DateTimeOriginal', exif.get('DateTimeDigitized', exif.get('DateTime')))
    image_dict['size'] = size

    # Return resulting dictionary
    return image_dict

def album_info_toml(conf_pair):
    """ Compile a dictionary of information on an album based on a conf pair """
    conf_path = "%s/%s" % conf_pair
    return toml.load(conf_path)


def album_info(conf_pair):
    """ Compile a dictionary of information on an album based on a conf pair """

    # Init dictionary
    album = {}
    images = []

    # Load conf
    conf_path = "%s/%s" % conf_pair
    images_path = conf_pair[0]
    with open(conf_path, 'r') as conf_file:
        conf = conf_file.readlines()

    # get album information
    for idx, conf_line in enumerate(conf):
        try:
            (name, value) = conf_line.split(" ::")
            value_stripped = value.strip("\n ").strip("\"")
        except ValueError:
            if conf_line.strip("\n") == "":
                print(("Line %i of the configuration is empty" % idx))
            else:
                print(("Malformed config line: '%s' (line %i)" % (conf_line.strip("\n"), idx+1)))
            exit()
        # Get information from images
        if "jpg" in name.lower():
            images.append(image_info(images_path, name, value_stripped))
            # Add 'album' as 'title'
        elif name.lower() == "album":
            album['title'] = value_stripped
        elif name.lower() == "galleries":
            album['galleries'] = value_stripped.split(", ")
        elif name.lower() == "public":
            album['public'] = value_stripped.lower() in ["true", "yes"]
        else:
            album[name.lower()] = value_stripped

    # Add images to album
    album["images"] = images

    return album


def gallery_info(directory, conf_name = "galleries.conf"):
    """ Compile a dictionary of information based on the galleries.conf file """
    # Load galleres.conf
    conf_path = "/".join([c for c in get_confs(directory, "conf") if c[1] == conf_name][0])

    # Parse configuration file
    with open(conf_path, 'r') as conf_file:
        conf = [l for l in conf_file.readlines() if len(l) > 1]

    # For each line, add it to a dict
    galleries = [{ "name" : l.split(" :: ")[0], "description" : l.split(" :: ")[1].strip("\n ").strip("\""), "albums" : [] } for l in conf]

    return galleries


def create_thumbnails(image_path, directory):
    """ Create thumbnails of an image """

    # Create thumbnails of the following sizes
    thumb_sizes = [(2000, 1500), (1600, 1200), (1280, 980), (1024, 768), (800, 600), (600, 450), (400, 300), (150, 150)]

    # Make sure directory exists
    if not os.path.exists(directory):
        os.mkdir(directory)

    # Open original image
    image_orig = Image.open(image_path)
    image = image_orig.copy()
    image_name = image_path.lower().split(".jpg")[0].split("/")[-1]
    orientation = 'horizontal' if image_orig.size[0] > image_orig.size[1] else 'vertical'

    # For each size produce an image of this size and save in directory
    for (thumb_width, thumb_height) in thumb_sizes:

        # Crop the square thumbnails
        if thumb_width == thumb_height:
            (width, height) = image.size
            if orientation == 'horizontal':
                margin = (width - height) / 2
                image = image.crop((margin, 0, width - margin, height))
            else:
                margin = (height - width) / 2
                image = image.crop((0, margin, width, height - margin))

        # Resize resulting image and save to directory
        image.thumbnail((thumb_width, thumb_height), Image.ANTIALIAS)

        # Save image
        thumb_path = "%s/%s_%ix%i.jpg" % (directory, image_name, thumb_width, thumb_height)
        image.save(thumb_path, "JPEG", quality=92)

    # Save original
    #orig_path = "%s/%s.jpg" % (directory, image_name)
    #image_orig.save(orig_path, "JPEG", quality=92)



class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%dT%H:%M:%S")
        return json.JSONEncoder.default(self, obj)



def process_album(album_pair, temp_root = "tmp", write_thumbnails = True):
    """ Compiles json file with information about album and writes thumbnails """

    (album_dir, album_conf) = album_pair

    # Gather information about album except if it's a malformed conf file
    try:
        info = album_info_toml((album_dir, album_conf))
    except Exception as e:
        print(("Error: %s (%s)" % (e, album_conf)))
        print((traceback.format_exc()))
        sys.exit(2)

    # Write info but make sure album directory exists
    if not os.path.exists(temp_root) : os.mkdir(temp_root)
    temp_dir = "%s/%s" % (temp_root, info['url'])
    if not os.path.exists(temp_dir) : os.mkdir(temp_dir)
    with open("%s/%s" % (temp_dir, "album.json"), 'w') as fp:
        json.dump(info, fp, cls=DateTimeEncoder)

    # For each image, save thumbnails
    if write_thumbnails:
        for im_data in info.get('images', []):
            im_file = "%s.jpg" % im_data['file']
            print(("processing %s" % (im_file)))
            image_path = find_image(album_dir, im_file)
            create_thumbnails(image_path, temp_dir)

    datetimes = [im['datetime'] for im in info['images'] if im.get('datetime')]
    if len(datetimes) > 0:
        info['timestamp'] = int(time.mktime(min(datetimes).timetuple()))
    else:
        info['timestamp'] = int(time.mktime(datetime.now().timetuple()))

    return (temp_dir, info)


def process_galleries(directory, conf_name = "galleries.conf", temp_root = "tmp"):
    """ Gather information about album except if it's a malformed conf file """
    try:
        info = gallery_info(directory, conf_name)
    except:
        print(("galleries.conf either doesn't exist in '%s' or doesn't contain valid data" % directory))
        return

    # Write info
    if not os.path.exists(temp_root) : os.mkdir(temp_root)
    json_path = "%s/galleries.json" % (temp_root)
    with open(json_path, 'w') as fp:
        json.dump(info, fp, separators=(',', ': '), indent = 2)

    # Push online
    push_galleries(json_path)
    # Delete json
    call(["rm", "-r", temp_root])




def push_galleries(json_path, host_dir = "photos", host = "dynkarken.com", user = "arnfred"):
    call(["rsync","-av", json_path, "%s@%s:~/%s" % (user, host, host_dir)])


def publish(directory, temp_dir = "tmp", write_thumbnails = True, skip = ["galleries.conf"], keep_temp = False, program_name = "photos"):
    configurations = get_confs(directory)
    if not os.path.exists(temp_dir) : os.mkdir(temp_dir)
    if len(configurations) == 0:
        print("No configuration files found. If you are using the old configuration format ('*.conf'), then run:\n> %s convert -d %s" % (program_name, directory))
    for c in configurations:
        if c[1] not in skip:
            print(("processing '%s'" % c[1]))
            (temp_dir, parsed_album) = process_album(c, temp_root = temp_dir, write_thumbnails = write_thumbnails)
            print(("pushing '%s'" % c[1]))
            upload(parsed_album, temp_dir)
            if keep_temp == False:
                print("removing temp dir")
                call(["rm","-r", temp_dir])

def convert(directory, skip = ["galleries.conf"], dry_run = False, keep_conf = True):
    configurations = get_confs(directory, "conf")
    for c in configurations:
        if c[1] not in skip:
            print(("parsing '%s'" % c[1]))
            parsed_album = album_info(c)
            # Remember to add photo time information
            print(("converting '%s' to toml" % c[1]))
            toml_album = toml.dumps(parsed_album)
            toml_path = "%s/%s.toml" % (c[0], c[1].split(".conf")[0])
            if dry_run:
                print(("This is a dry-run for converting %s to %s. Output:\n%s" % (c[1], toml_path, toml_album)))
            else:
                with open(toml_path, 'w') as f:
                    print(("Writing out to %s" % toml_path))
                    toml.dump(parsed_album, f)


# according to this guide: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html
def upload(album, temp_dir):
    # Fail fast in case environment isn't set
    albums_table = os.environ['ALBUMS_TABLE']
    images_bucket = os.environ['IMAGES_BUCKET']

    # For each file upload it to S3
    for im in album['images']:
        for (thumb_width, thumb_height) in thumb_sizes:
            thumb_name = "%s_%ix%i.jpg" % (im['file'], thumb_width, thumb_height)
            thumb_path = "%s/%s" % (temp_dir, thumb_name)
            s3_path = "albums/%s/%s" % (album['url'], thumb_name)
            print("Uploading %s to %s" % (thumb_path, s3_path))
            with open(thumb_path, 'rb') as f:
                s3.upload_fileobj(f, images_bucket, s3_path)

    # Upload config to dynamoDB
    table = dynamodb.Table(albums_table)
    for im in album['images']:
        im['datetime'] = im.get('datetime', datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")
    album_config = { 'id': album['url'], **album }
    pprint.pprint(album_config)
    table.put_item(Item=album_config)


# Run script if executed
if __name__ == "__main__":
    main(sys.argv[0], sys.argv[1:])
