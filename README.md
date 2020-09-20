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
env $(cat aws.prod.env) gunicorn upload:app --timeout 99999
```

Now you can access the server in your browser on `http://localhost:8000`. The `--timeout` is added to make sure gunicorn is patient and waits for the photo upload to complete before shutting down threads.

# Setting up Dokku

I'm adding a bit of info on setting up new services on my host here, since I don't have any information on that anywhere else.

To set up a new service, use this guide: http://dokku.viewdocs.io/dokku/deployment/application-deployment/

```
ssh dynkarken.com
dokku apps:create photo-tools
```

Then locally, add dynkarken as a git remote:

```
git remote add dynkarken dokku@dynkarken.com:photo-tools
```

Next to set up the environment for the app, copy the local env file and ssh onto dynkarken.com, then set the config for the app:

```
dokku config:set photo-tools <ENV key value pairs with = between>
```

To set up the domain, we use the instructions here: http://dokku.viewdocs.io/dokku/configuration/domains/

```
dokku domains:add photo-tools blah.ifany.org
```

# Adding ffmpeg to server

To use the ffmpeg binary from the python app, I've added a ffmpeg buildpack in the `.buildpacks` file



