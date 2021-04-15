import ffmpeg
import os
from pprint import pprint

from photos import find_file

def video_info(root, video_name, desc, published = True):
    """ Generate a dictionary of information about a video """
    # Init video dictionary
    extension = video_name[-4:]
    video_dict = {
        'file' : video_name.lower().split(extension)[0],
        'description' : desc.strip(" *"),
        'cover' : len(desc) > 1 and desc[-1] == '*',
        'banner' : len(desc) > 2 and desc[-2] == '*',
        'published': published
    }

    # Find video
    video_path = find_file(root, video_name)
    if video_path == None:
        raise Exception("Video %s doesn't exist in %s" % (video_name, root))

    # Define what exif data we are interested in and how it is translated
    video_info = ffmpeg.probe(video_path)['streams'][0]
    pprint(video_info),
    video_dict['datetime'] = video_info['tags']['creation_time'].split(".")[0]
    video_dict['size'] = [video_info['width'], video_info['height']]
    video_dict['is_video'] = True

    # Return resulting dictionary
    return video_dict

def extract_thumb(video_path, thumb_path, width):
    ffmpeg.input(video_path, ss=0).filter('scale', width, -1).output(thumb_path, vframes=1).run()

def reencode_to_mp4(filename, temp_dir):
    extension = filename[-4:]
    if extension == ".mp4":
        return filename
    else:
        video_path = os.path.join(temp_dir, filename)
        mp4_path = "{}.mp4".format(video_path.lower().split(extension)[0])
        ffmpeg.input(video_path).output(mp4_path).run()
        return "{}.mp4".format(filename.lower().split(extension)[0])
