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
gpg --decrypt < aws.env.gpg > aws.env # Password doesn't end in '?'
env $(cat aws.env) photos.py publish -d .
```



# Usage


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
