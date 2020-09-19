import ffmpeg

from photos import find_file

def video_info(root, video_name, desc, published = True):
    """ Generate a dictionary of information about a video """
    # Init video dictionary
    video_dict = {
        'file' : video_name.lower().split(".mp4")[0],
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
    video_info = ffmpeg.probe('VID_20200906_170652.mp4')['streams'][0]
    video_dict['datetime'] = video_info['tags']['creation_time']
    video_dict['size'] = [video_info['width'], video_info['height']]
    video_dict['is_video'] = True

    # Return resulting dictionary
    return video_dict
