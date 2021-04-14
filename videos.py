import ffmpeg

from photos import find_file

def video_info(root, video_name, desc, published = True):
    """ Generate a dictionary of information about a video """
    # Init video dictionary
    video_dict = {
        'file' : video_name.lower()[-4:],
        'extension' : video_name.lower()[-3:],
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
    video_dict['datetime'] = video_info['tags']['creation_time'].split(".")[0]
    video_dict['size'] = [video_info['width'], video_info['height']]
    video_dict['is_video'] = True

    # Return resulting dictionary
    return video_dict

def extract_thumb(video_path, thumb_path, width):
    ffmpeg.input(video_path, ss=0).filter('scale', width, -1).output(thumb_path, vframes=1).run()
