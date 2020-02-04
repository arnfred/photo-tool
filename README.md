Utils for uploading albums to my photo gallery. This code is oooold.

# Setup

## VirtualEnv

To set up a virtualenv, run the following.

```sh
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

## Env

To use the `aws.env` file you'll need to first decrypt it and then use `env` before running `photos.py`:

```
gpg --decrypt < aws.test.env.gpg > aws.test.env # Password doesn't end in '?'
env $(cat aws.test.env) photos.py publish -d .
```


# Photos Usage


```
# Create new album configuration file
./photos.py init -n <album name> [-p <conf path> -f <conf name>]

# Upload new version of gallery configuration file
./photos.py gallery -u [-p <gallery conf path>] 

# Convert old conf format to toml
./photos.py convert [-d <conf directory> -s <conf files to skip separated by ,> -q <enable dry-run>] 

# Publish albums
./photos.py publish -d <conf directory> [-w <upload images> -t <temp dir> -s <conf files to skip> -k <Keep temp dir>]
```

# Uploads Usage

To run the http server for the album edit page locally, first go through the steps for setting up a virtual environment and installing dependencies (listed above), then do the following:

```
export FLASK_APP=upload.py
env $(cat aws.test.env) flask run
```

Now you can access the server in your browser on `http://localhost:5000/album/<album_id>`. Try e.g. [album/koli](http://localhost:5000/album/koli).
